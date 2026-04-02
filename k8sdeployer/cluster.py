"""Cluster connection module supporting both kubeconfig and service account token authentication"""
import logging
import ssl
from typing import Optional

import kubernetes
from kubernetes.client import Configuration
from openshift.dynamic import DynamicClient
from openshift.dynamic.exceptions import NotFoundError

logger = logging.getLogger(__name__)


class ClusterConnection:
    """Manages connection to Kubernetes/OpenShift cluster"""
    
    def __init__(self, kubeconfig: Optional[str] = None, 
                 context: Optional[str] = None,
                 token: Optional[str] = None,
                 server: Optional[str] = None,
                 verify_ssl: bool = True):
        """
        Initialize cluster connection
        
        Args:
            kubeconfig: Path to kubeconfig file (defaults to ~/.kube/config)
            context: Kubeconfig context to use
            token: Service account token for authentication
            server: API server URL (required if using token)
            verify_ssl: Whether to verify SSL certificates
        """
        self.client = None
        self.token = None
        self.server = None
        self.verify_ssl = verify_ssl
        
        if token and server:
            self.connect_with_token(server, token)
        else:
            self.connect_with_kubeconfig(kubeconfig, context)
    
    def connect_with_kubeconfig(self, kubeconfig: Optional[str] = None, context: Optional[str] = None):
        """Connect using kubeconfig file"""
        try:
            if kubeconfig:
                kubernetes.config.load_kube_config(config_file=kubeconfig, context=context)
            else:
                kubernetes.config.load_kube_config(context=context)

            configuration = Configuration.get_default_copy()

            # Apply verify_ssl setting with proper precedence:
            # CLI flag (--insecure-skip-tls-verify) > Kubeconfig setting > Default
            if not self.verify_ssl:
                # CLI flag explicitly set to skip verification - override kubeconfig
                configuration.verify_ssl = False

            # Update instance variable to match actual configuration
            # (important for Ansible which reads self.cluster.verify_ssl)
            # This will be either:
            # - False if CLI flag was set, or
            # - Whatever load_kube_config() set based on kubeconfig (respects insecure-skip-tls-verify)
            self.verify_ssl = configuration.verify_ssl

            self.client = DynamicClient(kubernetes.client.ApiClient(configuration))

            # Extract token from kubeconfig
            api_key = configuration.get_api_key_with_prefix('authorization')
            if api_key:
                self.token = api_key.replace('Bearer', '').strip()

            # Get server URL
            self.server = configuration.host

            logger.info(f"Connected to cluster: {self.server}")

            # Validate connectivity early to fail fast on SSL errors
            self._validate_connection()
        except Exception as e:
            logger.error(f"Failed to connect with kubeconfig: {e}")
            raise
    
    def connect_with_token(self, server: str, token: str):
        """Connect using service account token"""
        try:
            self.token = token
            self.server = server.rstrip('/')
            
            configuration = Configuration()
            configuration.api_key = {'authorization': f"Bearer {token}"}
            configuration.host = self.server
            configuration.verify_ssl = self.verify_ssl
            
            self.client = DynamicClient(kubernetes.client.ApiClient(configuration))

            logger.info(f"Connected to cluster: {self.server} using token")

            # Validate connectivity early to fail fast on SSL errors
            self._validate_connection()
        except Exception as e:
            logger.error(f"Failed to connect with token: {e}")
            raise

    def _validate_connection(self):
        """Validate cluster connectivity by making a simple API call.

        This fails fast with a clear error message if there are SSL verification issues,
        but ignores permission errors since the user may not have cluster-level access.
        """
        try:
            # Make a simple API call to verify connectivity
            # Try to get API resources (doesn't require any specific permissions)
            self.client.resources.get(api_version='v1', kind='Namespace')
            logger.debug("Cluster connectivity validated successfully")
        except Exception as e:
            # Check if this is an SSL certificate verification error
            # Check both the exception type and error message for robustness
            is_ssl_error = False

            # Check exception type (most reliable)
            if isinstance(e, ssl.SSLError):
                is_ssl_error = True
            else:
                # Check error message as fallback (for wrapped SSL errors)
                error_msg = str(e).upper()
                if 'SSL' in error_msg and ('CERTIFICATE' in error_msg or 'VERIFY' in error_msg):
                    is_ssl_error = True

            if is_ssl_error:
                logger.error(
                    f"SSL certificate verification failed when connecting to {self.server}. "
                    f"Either:\n"
                    f"  1. Add 'insecure-skip-tls-verify: true' to your kubeconfig cluster configuration, or\n"
                    f"  2. Pass --insecure-skip-tls-verify flag to k8sdeploy, or\n"
                    f"  3. Add the cluster's CA certificate to your kubeconfig"
                )
                raise

            # Ignore other errors (like permission denied) - they'll surface later during actual operations
            logger.debug(f"Connectivity check completed (non-SSL error ignored): {str(e)}")

    def get(self, api_version: str, kind: str, name: str, namespace: Optional[str] = None):
        """Get a resource from the cluster"""
        try:
            resource = self.client.resources.get(api_version=api_version, kind=kind)
            if namespace:
                return resource.get(name=name, namespace=namespace)
            else:
                return resource.get(name=name)
        except NotFoundError:
            return None
        except Exception as e:
            logger.error(f"Error getting resource {kind}/{name}: {e}")
            raise
    
    def create(self, api_version: str, kind: str, body: dict, namespace: Optional[str] = None):
        """Create a resource in the cluster"""
        try:
            resource = self.client.resources.get(api_version=api_version, kind=kind)
            if namespace:
                return resource.create(body=body, namespace=namespace)
            else:
                return resource.create(body=body)
        except Exception as e:
            logger.error(f"Error creating resource {kind}: {e}")
            raise
    
    def delete(self, api_version: str, kind: str, name: str, namespace: Optional[str] = None):
        """Delete a resource from the cluster"""
        try:
            resource = self.client.resources.get(api_version=api_version, kind=kind)
            if namespace:
                return resource.delete(name=name, namespace=namespace)
            else:
                return resource.delete(name=name)
        except Exception as e:
            logger.error(f"Error deleting resource {kind}/{name}: {e}")
            raise
    
    def list(self, api_version: str, kind: str, namespace: Optional[str] = None, **kwargs):
        """List resources in the cluster"""
        try:
            resource = self.client.resources.get(api_version=api_version, kind=kind)
            if namespace:
                return resource.get(namespace=namespace, **kwargs)
            else:
                return resource.get(**kwargs)
        except Exception as e:
            logger.error(f"Error listing resources {kind}: {e}")
            raise
    
    def is_openshift(self) -> bool:
        """Check if cluster is OpenShift"""
        try:
            # Try to get OpenShift API resources
            self.client.resources.get(api_version='project.openshift.io/v1', kind='Project')
            return True
        except Exception:
            return False
    
    def get_version(self) -> str:
        """Get cluster version"""
        try:
            if self.is_openshift():
                cluster_version = self.client.resources.get(
                    api_version='config.openshift.io/v1',
                    kind='ClusterVersion'
                )
                version_info = cluster_version.get(name='version')
                return version_info.get('status', {}).get('desired', {}).get('version', 'unknown')
            else:
                # For Kubernetes, try to get version from API
                try:
                    version_info = self.client.resources.get(api_version='version', kind='Info').get()
                    return version_info.get('gitVersion', 'unknown')
                except Exception:
                    return 'unknown'
        except Exception:
            return 'unknown'

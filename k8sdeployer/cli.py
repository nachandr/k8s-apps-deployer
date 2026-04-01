"""Command-line interface for k8s-apps-deployer"""
import argparse
import sys
import logging
import json
import os
from typing import Optional

from k8sdeployer.cluster import ClusterConnection
from k8sdeployer.application_factory import ApplicationFactory


def setup_logging(verbose: bool = False):
    """Setup logging configuration"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def create_cluster_connection(args) -> ClusterConnection:
    """Create cluster connection from CLI arguments"""
    # Check for token-based auth
    token = os.environ.get('K8S_TOKEN') or args.token
    server = os.environ.get('K8S_SERVER') or args.server
    kubeconfig = args.kubeconfig or os.environ.get('KUBECONFIG')
    context = args.context
    verify_ssl = not args.insecure_skip_tls_verify
    
    if token and server:
        return ClusterConnection(token=token, server=server, verify_ssl=verify_ssl)
    else:
        return ClusterConnection(
            kubeconfig=kubeconfig,
            context=context,
            verify_ssl=verify_ssl
        )


def cmd_list(args):
    """List available applications"""
    factory = ApplicationFactory()
    apps = factory.get_all_app_ids()
    
    if apps:
        print("Available applications:")
        for app in sorted(apps):
            print(f"  - {app}")
    else:
        print("No applications available")


def cmd_deploy(args):
    """Deploy an application"""
    logger = logging.getLogger(__name__)
    
    try:
        cluster = create_cluster_connection(args)
        factory = ApplicationFactory()
        
        app = factory.create_app(args.application, cluster, args.namespace, logger)
        
        # Parse extra vars if provided
        extra_vars = {}
        if args.extra_vars:
            extra_vars = json.loads(args.extra_vars)
        
        logger.info(f'Deploying {args.application} in namespace: {app.namespace}')
        
        if args.force_cleanup:
            logger.info(f'Cleaning up application {args.application} before deploying')
            app.remove()
        
        if not app.deploy(extra_vars=extra_vars):
            logger.error("Application deployment failed")
            sys.exit(1)
        
        logger.info(f'Successfully deployed {args.application}')
        
    except Exception as e:
        logger.error(f"Deployment failed: {e}")
        sys.exit(1)


def cmd_remove(args):
    """Remove an application"""
    logger = logging.getLogger(__name__)
    
    try:
        cluster = create_cluster_connection(args)
        factory = ApplicationFactory()
        
        app = factory.create_app(args.application, cluster, args.namespace, logger)
        
        # Parse extra vars if provided
        extra_vars = {}
        if args.extra_vars:
            extra_vars = json.loads(args.extra_vars)

        logger.info(f'Removing {args.application} from namespace: {app.namespace}')
        
        if not app.remove(extra_vars=extra_vars):
            logger.error("Application removal failed")
            sys.exit(1)
        
        logger.info(f'Successfully removed {args.application}')
        
    except Exception as e:
        logger.error(f"Removal failed: {e}")
        sys.exit(1)


def cmd_validate(args):
    """Validate an application"""
    logger = logging.getLogger(__name__)
    
    try:
        cluster = create_cluster_connection(args)
        factory = ApplicationFactory()
        
        app = factory.create_app(args.application, cluster, args.namespace, logger)
        
        # Parse extra vars if provided
        extra_vars = {}
        if args.extra_vars:
            extra_vars = json.loads(args.extra_vars)

        logger.info(f'Validating {args.application} in namespace: {app.namespace}')
        
        if not app.validate(extra_vars=extra_vars):
            logger.error("Application validation failed")
            sys.exit(1)
        
        logger.info(f'Successfully validated {args.application}')
        
    except Exception as e:
        logger.error(f"Validation failed: {e}")
        sys.exit(1)


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description='K8s Apps Deployer - Deploy applications to Kubernetes/OpenShift',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Global arguments
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose logging')
    parser.add_argument('--kubeconfig', help='Path to kubeconfig file')
    parser.add_argument('--context', help='Kubeconfig context to use')
    parser.add_argument('--token', help='Service account token for authentication')
    parser.add_argument('--server', help='API server URL (required with --token)')
    parser.add_argument('--insecure-skip-tls-verify', action='store_true', 
                       help='Skip TLS certificate verification')
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List available applications')
    
    # Deploy command
    deploy_parser = subparsers.add_parser('deploy', help='Deploy an application')
    deploy_parser.add_argument('application', help='Application name to deploy')
    deploy_parser.add_argument('-n', '--namespace', help='Namespace to deploy to')
    deploy_parser.add_argument('-f', '--force-cleanup', action='store_true',
                              help='Cleanup application before deploying')
    deploy_parser.add_argument('-e', '--extra-vars', help='Extra variables as JSON string')
    
    # Remove command
    remove_parser = subparsers.add_parser('remove', help='Remove an application')
    remove_parser.add_argument('application', help='Application name to remove')
    remove_parser.add_argument('-n', '--namespace', help='Namespace to remove from')
    remove_parser.add_argument('-e', '--extra-vars', help='Extra variables as JSON string')
    
    # Validate command
    validate_parser = subparsers.add_parser('validate', help='Validate an application')
    validate_parser.add_argument('application', help='Application name to validate')
    validate_parser.add_argument('-n', '--namespace', help='Namespace to validate in')
    validate_parser.add_argument('-e', '--extra-vars', help='Extra variables as JSON string')
    
    args = parser.parse_args()
    
    setup_logging(args.verbose)
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    if args.command == 'list':
        cmd_list(args)
    elif args.command == 'deploy':
        cmd_deploy(args)
    elif args.command == 'remove':
        cmd_remove(args)
    elif args.command == 'validate':
        cmd_validate(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()

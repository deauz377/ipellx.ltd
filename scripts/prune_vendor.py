#!/usr/bin/env python3
"""Strip unused AWS service definitions from botocore/boto3 after install.

django-storages[s3] pulls in boto3, which vendors botocore's full API
catalogue for every AWS service (EC2, DynamoDB, Lambda, ...). Only S3 is ever
used here, but the catalogue alone is large enough to push the Vercel
function bundle over its 225 MB limit. Keeping just the service data this
app actually calls (S3, and STS/SSO which botocore's credential resolution
imports even when unused) removes tens of megabytes with no behaviour change.
Run after `pip install`, before Vercel bundles the function.
"""
import os
import shutil

KEEP_SERVICES = {'s3', 'sts', 'sso', 'sso-oidc'}


def prune_data_dir(data_dir):
    if not os.path.isdir(data_dir):
        return
    removed = 0
    for entry in os.listdir(data_dir):
        path = os.path.join(data_dir, entry)
        if os.path.isdir(path) and entry not in KEEP_SERVICES:
            shutil.rmtree(path, ignore_errors=True)
            removed += 1
    print(f'Pruned {removed} unused service dirs from {data_dir}')


def prune_pycache(root):
    for dirpath, dirnames, _filenames in os.walk(root):
        if '__pycache__' in dirnames:
            shutil.rmtree(os.path.join(dirpath, '__pycache__'), ignore_errors=True)
            dirnames.remove('__pycache__')


def main():
    try:
        import botocore
    except ImportError:
        print('botocore not installed; nothing to prune.')
        return

    botocore_dir = os.path.dirname(botocore.__file__)
    prune_data_dir(os.path.join(botocore_dir, 'data'))

    try:
        import boto3
        boto3_dir = os.path.dirname(boto3.__file__)
        prune_data_dir(os.path.join(boto3_dir, 'data'))
    except ImportError:
        pass

    site_packages = os.path.dirname(botocore_dir)
    prune_pycache(site_packages)


if __name__ == '__main__':
    main()

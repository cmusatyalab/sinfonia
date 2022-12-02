#
# Sinfonia
#
# Copyright (c) 2022 Carnegie Mellon University
#
# SPDX-License-Identifier: MIT
#

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import boto3
from tqdm import tqdm


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--aws-creds",
        default="aws_creds.json",
        type=argparse.FileType("r"),
        help="extra args (AWS credentials) for boto3.resource(s3) [aws_creds.json]",
    )
    parser.add_argument(
        "bucket_name",
        help="S3 bucket to store recipes",
    )
    parser.add_argument(
        "RECIPES",
        type=Path,
        nargs="?",
        default="RECIPES",
        help="recipes folder to upload",
    )
    parser.add_argument(
        "--create", action="store_true", help="Create bucket if it doesn't exist"
    )
    parser.add_argument(
        "--update", action="store_true", help="Re-upload already existing recipes"
    )
    parser.add_argument(
        "--delete", action="store_true", help="Remove old recipes from S3 bucket"
    )
    parser.add_argument(
        "--public", action="store_true", help="Make recipes readable by anyone"
    )
    return parser.parse_args()


def main() -> int:
    """Push Sinfonia recipes to an S3 bucket"""
    args = parse_args()

    # check if source folder exists
    if not args.RECIPES:
        print(f"Missing {args.RECIPES}")
        return 1

    # connect to S3 resource
    creds = json.load(args.aws_creds)
    s3 = boto3.resource("s3", **creds)

    # make sure bucket exists
    bucket = s3.Bucket(args.bucket_name)
    if args.create:
        bucket.create()
        bucket.wait_until_exists()

    # list existing recipes in bucket (also tests if bucket exists)
    try:
        existing = {item.key for item in bucket.objects.all()}
    except s3.meta.client.exceptions.NoSuchBucket:
        print(f"Bucket {args.bucket_name} does not exist")
        return 1

    with tqdm(list(args.RECIPES.iterdir())) as recipes:
        ACL = dict(ACL="public-read" if args.public else "private")
        for recipe in recipes:
            if args.update or recipe.name not in existing:
                action = "Updating" if recipe.name in existing else "Creating"
                recipes.set_description(f"{action} {recipe.name}")

                with recipe.open("rb") as fh:
                    bucket.upload_fileobj(fh, recipe.name, ExtraArgs=ACL)
            existing.discard(recipe.name)

    if args.delete and existing:
        if input(f"Ok to delete {len(existing)} old recipes? [yN] ") != "y":
            return 0

        for key in tqdm(existing):
            bucket.Object(key).delete()

    return 0


if __name__ == "__main__":
    sys.exit(main())

# storage/r2.py
"""
Cloudflare R2 Storage Module
Handles all interactions with Cloudflare R2 for storing scraped news data and images.

Folder Structure:
    bucket/
    └── 2026/
        └── January/
            └── Week-1/
                └── 2026-01-04/
                    ├── archdaily.json
                    ├── dezeen.json
                    └── images/
                        ├── archdaily-article-slug.jpg
                        └── dezeen-project-name.jpg
"""

import os
import json
import re
from datetime import datetime, date
from typing import Optional, Tuple
from urllib.parse import urlparse
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


class R2Storage:
    """Handles Cloudflare R2 storage operations."""

    def __init__(
        self,
        account_id: Optional[str] = None,
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        bucket_name: Optional[str] = None,
        public_url: Optional[str] = None
    ):
        """
        Initialize R2 storage client.

        Args:
            account_id: Cloudflare account ID (defaults to R2_ACCOUNT_ID env var)
            access_key_id: R2 access key (defaults to R2_ACCESS_KEY_ID env var)
            secret_access_key: R2 secret key (defaults to R2_SECRET_ACCESS_KEY env var)
            bucket_name: R2 bucket name (defaults to R2_BUCKET_NAME env var)
            public_url: Public URL for the bucket (defaults to R2_PUBLIC_URL env var)
        """
        self.account_id = account_id or os.getenv("R2_ACCOUNT_ID")
        self.access_key_id = access_key_id or os.getenv("R2_ACCESS_KEY_ID")
        self.secret_access_key = secret_access_key or os.getenv("R2_SECRET_ACCESS_KEY")
        self.bucket_name = bucket_name or os.getenv("R2_BUCKET_NAME")
        self.public_url = public_url or os.getenv("R2_PUBLIC_URL")

        # Validate required credentials
        missing: list[str] = []
        if not self.account_id:
            missing.append("R2_ACCOUNT_ID")
        if not self.access_key_id:
            missing.append("R2_ACCESS_KEY_ID")
        if not self.secret_access_key:
            missing.append("R2_SECRET_ACCESS_KEY")
        if not self.bucket_name:
            missing.append("R2_BUCKET_NAME")

        if missing:
            raise ValueError(f"Missing R2 credentials: {', '.join(missing)}")

        # Create S3 client configured for R2
        self.client = boto3.client(
            "s3",
            endpoint_url=f"https://{self.account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "standard"}
            )
        )

    def _get_week_number(self, dt: date) -> int:
        """Get the week number within the month (1-5)."""
        first_day = dt.replace(day=1)
        day_of_month = dt.day
        first_weekday = first_day.weekday()
        adjusted_day = day_of_month + first_weekday
        week_number = (adjusted_day - 1) // 7 + 1
        return week_number

    def _build_path(self, source: str, target_date: Optional[date] = None) -> str:
        """
        Build the storage path based on date.

        Format: YYYY/MonthName/Week-N/YYYY-MM-DD/source.json
        """
        if target_date is None:
            target_date = date.today()

        year = target_date.year
        month_name = target_date.strftime("%B")
        week_num = self._get_week_number(target_date)
        date_str = target_date.strftime("%Y-%m-%d")

        return f"{year}/{month_name}/Week-{week_num}/{date_str}/{source}.json"

    def _build_image_path(
        self, 
        source: str, 
        article_slug: str, 
        extension: str = "jpg",
        target_date: Optional[date] = None
    ) -> str:
        """
        Build the storage path for an image.

        Format: YYYY/MonthName/Week-N/YYYY-MM-DD/images/source-slug.ext
        """
        if target_date is None:
            target_date = date.today()

        year = target_date.year
        month_name = target_date.strftime("%B")
        week_num = self._get_week_number(target_date)
        date_str = target_date.strftime("%Y-%m-%d")
        clean_slug = self._slugify(article_slug)

        return f"{year}/{month_name}/Week-{week_num}/{date_str}/images/{source}-{clean_slug}.{extension}"

    def _slugify(self, text: str, max_length: int = 50) -> str:
        """Convert text to URL-safe slug."""
        if not text:
            return "untitled"

        slug = text.lower()
        slug = re.sub(r'[^\w\s-]', '', slug)
        slug = re.sub(r'[-\s]+', '-', slug)
        slug = slug.strip('-')

        if len(slug) > max_length:
            slug = slug[:max_length].rstrip('-')

        return slug or "untitled"

    def _get_image_extension(self, url: str, content_type: Optional[str] = None) -> str:
        """Determine image extension from URL or content type."""
        if content_type:
            mime_map = {
                'image/jpeg': 'jpg',
                'image/jpg': 'jpg',
                'image/png': 'png',
                'image/webp': 'webp',
                'image/gif': 'gif',
                'image/svg+xml': 'svg',
            }
            ext = mime_map.get(content_type.lower().split(';')[0])
            if ext:
                return ext

        parsed = urlparse(url)
        path = parsed.path.lower()

        for ext in ['jpg', 'jpeg', 'png', 'webp', 'gif', 'svg']:
            if path.endswith(f'.{ext}'):
                return 'jpg' if ext == 'jpeg' else ext

        return 'jpg'

    def _get_content_type(self, extension: str) -> str:
        """Get MIME type for file extension."""
        content_types = {
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'png': 'image/png',
            'webp': 'image/webp',
            'gif': 'image/gif',
            'svg': 'image/svg+xml',
        }
        return content_types.get(extension, 'image/jpeg')

    # =========================================================================
    # Article Storage
    # =========================================================================

    def save_articles(
        self, 
        articles: list[dict], 
        source: str,
        target_date: Optional[date] = None,
        metadata: Optional[dict] = None
    ) -> str:
        """Save articles to R2 storage."""
        path = self._build_path(source, target_date)
        actual_date = target_date or date.today()

        data: dict = {
            "source": source,
            "date": actual_date.isoformat(),
            "fetched_at": datetime.now().isoformat(),
            "article_count": len(articles),
            "articles": articles
        }

        if metadata:
            data["metadata"] = metadata

        self.client.put_object(
            Bucket=self.bucket_name,
            Key=path,
            Body=json.dumps(data, indent=2, ensure_ascii=False),
            ContentType="application/json"
        )

        print(f"   📁 Saved {len(articles)} articles to: {path}")
        return path

    def get_articles(
        self, 
        source: str, 
        target_date: Optional[date] = None
    ) -> Optional[dict]:
        """Retrieve articles from R2 storage."""
        path = self._build_path(source, target_date)

        try:
            response = self.client.get_object(
                Bucket=self.bucket_name,
                Key=path
            )
            content = response["Body"].read().decode("utf-8")
            return json.loads(content)
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                return None
            raise

    # =========================================================================
    # Image Storage
    # =========================================================================

    def save_image(
        self,
        image_bytes: bytes,
        source: str,
        article_slug: str,
        image_url: Optional[str] = None,
        content_type: Optional[str] = None,
        target_date: Optional[date] = None
    ) -> Tuple[str, Optional[str]]:
        """
        Save an image to R2 storage.

        Returns:
            Tuple of (storage_path, public_url or None)
        """
        if not image_bytes:
            raise ValueError("No image data provided")

        extension = self._get_image_extension(image_url or "", content_type)
        path = self._build_image_path(source, article_slug, extension, target_date)
        upload_content_type = self._get_content_type(extension)

        self.client.put_object(
            Bucket=self.bucket_name,
            Key=path,
            Body=image_bytes,
            ContentType=upload_content_type,
            CacheControl="public, max-age=31536000"
        )

        public_url: Optional[str] = None
        if self.public_url:
            public_url = f"{self.public_url.rstrip('/')}/{path}"

        print(f"   🖼️ Saved image: {path} ({len(image_bytes)} bytes)")
        return path, public_url

    def save_hero_image(
        self,
        image_bytes: bytes,
        article: dict,
        source: str,
        target_date: Optional[date] = None
    ) -> Optional[dict]:
        """Save hero image for an article and return updated hero_image dict."""
        hero_image = article.get("hero_image")
        if not hero_image:
            return None

        slug = article.get("title", "")
        if not slug:
            url = article.get("link", "")
            if url:
                parsed = urlparse(url)
                slug = parsed.path.split("/")[-1] or parsed.path.split("/")[-2] or "article"

        try:
            path, public_url = self.save_image(
                image_bytes=image_bytes,
                source=source,
                article_slug=slug,
                image_url=hero_image.get("url"),
                target_date=target_date
            )

            hero_image["r2_path"] = path
            hero_image["r2_url"] = public_url
            hero_image["saved_at"] = datetime.now().isoformat()

            return hero_image

        except Exception as e:
            print(f"   ⚠️ Failed to save hero image: {e}")
            return hero_image

    def get_image(self, path: str) -> Optional[bytes]:
        """Retrieve an image from R2 storage."""
        try:
            response = self.client.get_object(
                Bucket=self.bucket_name,
                Key=path
            )
            return response["Body"].read()
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                return None
            raise

    def image_exists(self, path: str) -> bool:
        """Check if an image exists at the given path."""
        try:
            self.client.head_object(Bucket=self.bucket_name, Key=path)
            return True
        except ClientError:
            return False

    # =========================================================================
    # Listing & Utilities
    # =========================================================================

    def list_dates(
        self, 
        source: Optional[str] = None,
        year: Optional[int] = None, 
        month: Optional[str] = None
    ) -> list[str]:
        """List available dates in storage."""
        prefix = ""
        if year:
            prefix = f"{year}/"
            if month:
                prefix = f"{year}/{month}/"

        try:
            response = self.client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix,
                Delimiter="/"
            )

            dates: list[str] = []
            if "Contents" in response:
                for obj in response["Contents"]:
                    key = obj["Key"]
                    if source is None or key.endswith(f"/{source}.json"):
                        dates.append(key)

            return dates
        except ClientError as e:
            print(f"Error listing dates: {e}")
            return []

    def list_images(
        self,
        source: Optional[str] = None,
        target_date: Optional[date] = None
    ) -> list[str]:
        """List images for a given date."""
        actual_date = target_date or date.today()

        year = actual_date.year
        month_name = actual_date.strftime("%B")
        week_num = self._get_week_number(actual_date)
        date_str = actual_date.strftime("%Y-%m-%d")

        prefix = f"{year}/{month_name}/Week-{week_num}/{date_str}/images/"

        try:
            response = self.client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )

            images: list[str] = []
            if "Contents" in response:
                for obj in response["Contents"]:
                    key = obj["Key"]
                    if source is None or key.startswith(f"{prefix}{source}-"):
                        images.append(key)

            return images
        except ClientError as e:
            print(f"Error listing images: {e}")
            return []

    def file_exists(self, source: str, target_date: Optional[date] = None) -> bool:
        """Check if a file exists for the given source and date."""
        path = self._build_path(source, target_date)

        try:
            self.client.head_object(Bucket=self.bucket_name, Key=path)
            return True
        except ClientError:
            return False

    def delete_file(self, source: str, target_date: Optional[date] = None) -> bool:
        """Delete a file from storage."""
        path = self._build_path(source, target_date)

        try:
            self.client.delete_object(Bucket=self.bucket_name, Key=path)
            print(f"   🗑️ Deleted: {path}")
            return True
        except ClientError as e:
            print(f"   ❌ Delete failed: {e}")
            return False

    def test_connection(self) -> bool:
        """Test R2 connection and bucket access."""
        try:
            self.client.list_objects_v2(
                Bucket=self.bucket_name,
                MaxKeys=1
            )
            print(f"   ✅ R2 connected: bucket '{self.bucket_name}'")
            if self.public_url:
                print(f"   ✅ Public URL: {self.public_url}")
            return True
        except ClientError as e:
            print(f"   ❌ R2 connection failed: {e}")
            return False
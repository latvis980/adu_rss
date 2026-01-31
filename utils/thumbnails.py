# utils/thumbnail.py
"""
Thumbnail Generation Utility for ADUmedia

Generates square 400x400px thumbnails from article images.
Stores both full-size and thumbnail versions in R2.
"""

import io
from typing import Optional, Tuple
from PIL import Image
import requests


class ThumbnailGenerator:
    """Generate and process thumbnails for article images."""
    
    # Target thumbnail size (square)
    THUMBNAIL_SIZE = (400, 400)
    THUMBNAIL_QUALITY = 85
    THUMBNAIL_FORMAT = "JPEG"
    
    @staticmethod
    def download_image(url: str, timeout: int = 30) -> Optional[bytes]:
        """
        Download image from URL.
        
        Args:
            url: Image URL
            timeout: Request timeout in seconds
            
        Returns:
            Image bytes or None if failed
        """
        try:
            response = requests.get(
                url, 
                timeout=timeout,
                headers={"User-Agent": "ADUmedia/1.0"}
            )
            response.raise_for_status()
            return response.content
        except Exception as e:
            print(f"      ❌ Failed to download image: {e}")
            return None
    
    @staticmethod
    def create_thumbnail(
        image_bytes: bytes,
        size: Tuple[int, int] = None
    ) -> Optional[bytes]:
        """
        Create a square thumbnail by center-cropping and resizing.
        
        Args:
            image_bytes: Original image bytes
            size: Target size (width, height), defaults to THUMBNAIL_SIZE
            
        Returns:
            Thumbnail bytes (JPEG) or None if failed
        """
        if size is None:
            size = ThumbnailGenerator.THUMBNAIL_SIZE
        
        try:
            # Open image
            img = Image.open(io.BytesIO(image_bytes))
            
            # Convert to RGB if needed (handles RGBA, grayscale, etc.)
            if img.mode != "RGB":
                # For RGBA, paste on white background
                if img.mode == "RGBA":
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[3])  # Use alpha channel as mask
                    img = background
                else:
                    img = img.convert("RGB")
            
            # Get dimensions
            width, height = img.size
            
            # Calculate crop box for center square
            if width > height:
                # Landscape: crop sides
                left = (width - height) // 2
                right = left + height
                top = 0
                bottom = height
            else:
                # Portrait or square: crop top/bottom
                top = (height - width) // 2
                bottom = top + width
                left = 0
                right = width
            
            # Crop to square
            img_cropped = img.crop((left, top, right, bottom))
            
            # Resize to target size
            img_thumbnail = img_cropped.resize(size, Image.Resampling.LANCZOS)
            
            # Save to bytes
            output = io.BytesIO()
            img_thumbnail.save(
                output,
                format=ThumbnailGenerator.THUMBNAIL_FORMAT,
                quality=ThumbnailGenerator.THUMBNAIL_QUALITY,
                optimize=True
            )
            
            return output.getvalue()
            
        except Exception as e:
            print(f"      ❌ Failed to create thumbnail: {e}")
            return None
    
    @staticmethod
    def process_and_upload(
        r2_storage,
        image_url: str,
        full_path: str,
        thumbnail_path: str,
        download_timeout: int = 30
    ) -> Tuple[bool, bool]:
        """
        Download image, create thumbnail, and upload both to R2.
        
        Args:
            r2_storage: R2Storage instance
            image_url: URL of original image
            full_path: R2 path for full-size image
            thumbnail_path: R2 path for thumbnail
            download_timeout: Download timeout in seconds
            
        Returns:
            Tuple of (full_uploaded, thumbnail_uploaded)
        """
        # Download original
        print(f"      📥 Downloading image...")
        image_bytes = ThumbnailGenerator.download_image(image_url, download_timeout)
        
        if not image_bytes:
            return (False, False)
        
        # Upload full-size
        full_uploaded = False
        try:
            r2_storage.client.put_object(
                Bucket=r2_storage.bucket_name,
                Key=full_path,
                Body=image_bytes,
                ContentType="image/jpeg"
            )
            full_uploaded = True
            print(f"      ✅ Uploaded full-size: {full_path}")
        except Exception as e:
            print(f"      ❌ Failed to upload full-size: {e}")
        
        # Create and upload thumbnail
        thumbnail_uploaded = False
        print(f"      🎨 Creating thumbnail...")
        thumbnail_bytes = ThumbnailGenerator.create_thumbnail(image_bytes)
        
        if thumbnail_bytes:
            try:
                r2_storage.client.put_object(
                    Bucket=r2_storage.bucket_name,
                    Key=thumbnail_path,
                    Body=thumbnail_bytes,
                    ContentType="image/jpeg"
                )
                thumbnail_uploaded = True
                
                # Calculate size reduction
                original_kb = len(image_bytes) / 1024
                thumbnail_kb = len(thumbnail_bytes) / 1024
                reduction = ((original_kb - thumbnail_kb) / original_kb) * 100
                
                print(f"      ✅ Uploaded thumbnail: {thumbnail_path}")
                print(f"         📊 Size: {original_kb:.1f}KB → {thumbnail_kb:.1f}KB ({reduction:.0f}% smaller)")
            except Exception as e:
                print(f"      ❌ Failed to upload thumbnail: {e}")
        
        return (full_uploaded, thumbnail_uploaded)


def get_thumbnail_path(full_image_path: str) -> str:
    """
    Convert full image path to thumbnail path by adding '_thumb' suffix.
    
    Example:
        "2026/January/Week-5/2026-01-30/images/archdaily_001.jpg"
        → "2026/January/Week-5/2026-01-30/images/archdaily_001_thumb.jpg"
    
    Args:
        full_image_path: Path to full-size image
        
    Returns:
        Path for thumbnail
    """
    # Split filename and extension
    if "." in full_image_path:
        base, ext = full_image_path.rsplit(".", 1)
        return f"{base}_thumb.{ext}"
    else:
        return f"{full_image_path}_thumb"

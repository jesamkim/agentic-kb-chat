"""
S3 이미지 처리 유틸리티
Citation에서 사용할 S3 이미지 관련 기능들
"""

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse
import logging
from config.settings import settings

logger = logging.getLogger(__name__)


class S3ImageHandler:
    """S3 이미지 처리 클래스"""
    
    def __init__(self):
        try:
            self.s3_client = boto3.client('s3', region_name=settings.model.region)
        except NoCredentialsError:
            logger.warning("AWS credentials not found. S3 functionality will be limited.")
            self.s3_client = None
    
    def generate_presigned_url(self, s3_uri: str, expiration: int = 3600) -> Optional[str]:
        """S3 URI에서 presigned URL 생성"""
        if not self.s3_client:
            logger.warning("S3 client not available. Cannot generate presigned URL.")
            return None
        
        try:
            # S3 URI 파싱
            parsed = urlparse(s3_uri)
            if parsed.scheme != 's3':
                logger.error(f"Invalid S3 URI: {s3_uri}")
                return None
            
            bucket_name = parsed.netloc
            object_key = parsed.path.lstrip('/')
            
            # presigned URL 생성
            presigned_url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket_name, 'Key': object_key},
                ExpiresIn=expiration
            )
            
            return presigned_url
            
        except ClientError as e:
            logger.error(f"Error generating presigned URL for {s3_uri}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error generating presigned URL: {e}")
            return None
    
    def get_image_metadata(self, s3_uri: str) -> Optional[Dict[str, Any]]:
        """S3 이미지의 메타데이터 조회"""
        if not self.s3_client:
            return None
        
        try:
            parsed = urlparse(s3_uri)
            if parsed.scheme != 's3':
                return None
            
            bucket_name = parsed.netloc
            object_key = parsed.path.lstrip('/')
            
            # 객체 메타데이터 조회
            response = self.s3_client.head_object(Bucket=bucket_name, Key=object_key)
            
            metadata = {
                'content_type': response.get('ContentType'),
                'content_length': response.get('ContentLength'),
                'last_modified': response.get('LastModified'),
                'etag': response.get('ETag'),
                'metadata': response.get('Metadata', {})
            }
            
            return metadata
            
        except ClientError as e:
            logger.error(f"Error getting metadata for {s3_uri}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting metadata: {e}")
            return None
    
    def check_image_accessibility(self, s3_uri: str) -> bool:
        """이미지 접근 가능성 확인"""
        if not self.s3_client:
            return False
        
        try:
            parsed = urlparse(s3_uri)
            if parsed.scheme != 's3':
                return False
            
            bucket_name = parsed.netloc
            object_key = parsed.path.lstrip('/')
            
            # 객체 존재 여부 확인
            self.s3_client.head_object(Bucket=bucket_name, Key=object_key)
            return True
            
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                logger.warning(f"Image not found: {s3_uri}")
            else:
                logger.error(f"Error checking image accessibility: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error checking accessibility: {e}")
            return False
    
    def get_image_dimensions_from_metadata(self, metadata: Dict[str, Any]) -> tuple[Optional[int], Optional[int]]:
        """메타데이터에서 이미지 크기 추출"""
        try:
            # S3 메타데이터에서 이미지 크기 정보 추출
            custom_metadata = metadata.get('metadata', {})
            
            width = custom_metadata.get('width')
            height = custom_metadata.get('height')
            
            if width and height:
                return int(width), int(height)
            
            # 다른 형태의 메타데이터에서 추출 시도
            if 'image-width' in custom_metadata and 'image-height' in custom_metadata:
                return int(custom_metadata['image-width']), int(custom_metadata['image-height'])
            
            return None, None
            
        except (ValueError, TypeError):
            return None, None


# 전역 S3 핸들러 인스턴스
s3_handler = S3ImageHandler()


def enhance_citation_with_s3_info(citation_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Citation 딕셔너리에 S3 정보 추가"""
    if not citation_dict.get('has_images'):
        return citation_dict
    
    enhanced_citation = citation_dict.copy()
    
    # 각 이미지에 대해 presigned URL 생성
    if 'images' in enhanced_citation:
        for img in enhanced_citation['images']:
            s3_uri = img.get('s3_uri')
            if s3_uri:
                # presigned URL 생성
                presigned_url = s3_handler.generate_presigned_url(s3_uri)
                if presigned_url:
                    img['presigned_url'] = presigned_url
                
                # 접근 가능성 확인
                img['accessible'] = s3_handler.check_image_accessibility(s3_uri)
                
                # 메타데이터 조회 (선택적)
                if img.get('accessible'):
                    metadata = s3_handler.get_image_metadata(s3_uri)
                    if metadata:
                        # 파일 크기 업데이트
                        if not img.get('file_size') and metadata.get('content_length'):
                            img['file_size'] = metadata['content_length']
                        
                        # 이미지 크기 업데이트
                        if not img.get('width') or not img.get('height'):
                            width, height = s3_handler.get_image_dimensions_from_metadata(metadata)
                            if width and height:
                                img['width'] = width
                                img['height'] = height
    
    # 주요 이미지에도 동일한 처리
    if 'primary_image' in enhanced_citation:
        primary_img = enhanced_citation['primary_image']
        s3_uri = primary_img.get('s3_uri')
        if s3_uri:
            presigned_url = s3_handler.generate_presigned_url(s3_uri)
            if presigned_url:
                primary_img['presigned_url'] = presigned_url
            primary_img['accessible'] = s3_handler.check_image_accessibility(s3_uri)
    
    return enhanced_citation


def batch_enhance_citations_with_s3_info(citations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """여러 Citation을 일괄 처리하여 S3 정보 추가"""
    enhanced_citations = []
    
    for citation in citations:
        enhanced_citation = enhance_citation_with_s3_info(citation)
        enhanced_citations.append(enhanced_citation)
    
    return enhanced_citations

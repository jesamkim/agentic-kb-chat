"""
Citation 처리 유틸리티
RAG 검색 결과의 출처 정보를 관리하고 처리합니다.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
import hashlib
import json
import re
from urllib.parse import urlparse


@dataclass
class ImageInfo:
    """이미지 정보 데이터 모델"""
    s3_uri: str                          # S3 이미지 URI
    image_type: str = "png"              # 이미지 타입 (png, jpg, etc.)
    alt_text: Optional[str] = None       # 대체 텍스트
    caption: Optional[str] = None        # 이미지 캡션
    width: Optional[int] = None          # 이미지 너비
    height: Optional[int] = None         # 이미지 높이
    file_size: Optional[int] = None      # 파일 크기 (bytes)
    
    def get_presigned_url(self, expiration: int = 3600) -> Optional[str]:
        """S3 presigned URL 생성 (향후 구현)"""
        # TODO: boto3를 사용하여 presigned URL 생성
        return None
    
    def is_valid_s3_uri(self) -> bool:
        """S3 URI 유효성 검증"""
        try:
            parsed = urlparse(self.s3_uri)
            return parsed.scheme == 's3' and bool(parsed.netloc) and bool(parsed.path)
        except:
            return False
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "s3_uri": self.s3_uri,
            "image_type": self.image_type,
            "alt_text": self.alt_text,
            "caption": self.caption,
            "width": self.width,
            "height": self.height,
            "file_size": self.file_size
        }


@dataclass
class Citation:
    """Citation 데이터 모델 (이미지 지원 포함)"""
    id: str                           # 고유 식별자
    document_uri: str                 # 문서 URI
    document_title: str               # 문서 제목
    chunk_text: str                   # 관련 텍스트 chunk
    page_number: Optional[int] = None # 페이지 번호
    confidence_score: float = 0.0     # ReRank 점수
    relevance_score: float = 0.0      # 원본 검색 점수
    metadata: Dict[str, Any] = field(default_factory=dict)  # 추가 메타데이터
    created_at: datetime = field(default_factory=datetime.now)
    
    # 이미지 관련 필드 추가
    images: List[ImageInfo] = field(default_factory=list)  # 연관된 이미지들
    content_type: str = "text"        # "text", "image", "mixed"
    
    def __post_init__(self):
        """Citation ID 자동 생성 및 컨텐츠 타입 결정"""
        if not self.id:
            # 문서 URI와 chunk 텍스트 기반으로 고유 ID 생성
            content = f"{self.document_uri}:{self.chunk_text[:100]}"
            self.id = hashlib.md5(content.encode()).hexdigest()[:12]
        
        # 컨텐츠 타입 자동 결정
        if self.images and self.chunk_text.strip():
            self.content_type = "mixed"
        elif self.images and not self.chunk_text.strip():
            self.content_type = "image"
        else:
            self.content_type = "text"
    
    def add_image(self, image_info: ImageInfo) -> None:
        """이미지 정보 추가"""
        if image_info.is_valid_s3_uri():
            self.images.append(image_info)
            # 컨텐츠 타입 업데이트
            if self.chunk_text.strip():
                self.content_type = "mixed"
            else:
                self.content_type = "image"
    
    def has_images(self) -> bool:
        """이미지 포함 여부 확인"""
        return len(self.images) > 0
    
    def get_primary_image(self) -> Optional[ImageInfo]:
        """주요 이미지 반환 (첫 번째 이미지)"""
        return self.images[0] if self.images else None
    
    def get_preview_text(self, max_length: int = 200) -> str:
        """미리보기용 텍스트 반환"""
        if len(self.chunk_text) <= max_length:
            return self.chunk_text
        return self.chunk_text[:max_length] + "..."
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "id": self.id,
            "document_uri": self.document_uri,
            "document_title": self.document_title,
            "chunk_text": self.chunk_text,
            "page_number": self.page_number,
            "confidence_score": self.confidence_score,
            "relevance_score": self.relevance_score,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "content_type": self.content_type,
            "images": [img.to_dict() for img in self.images],
            "has_images": self.has_images()
        }
    
    @classmethod
    def from_kb_result(cls, kb_result: Dict[str, Any], confidence_score: float = 0.0) -> 'Citation':
        """Bedrock KB 검색 결과에서 Citation 생성 (이미지 지원 포함)"""
        content = kb_result.get('content', {})
        metadata = kb_result.get('metadata', {})
        location = kb_result.get('location', {})
        
        # S3 URI에서 파일명 추출 (우선순위 순서)
        document_uri = ""
        document_title = "Unknown Document"
        
        # 1. location에서 S3 URI 추출 (가장 신뢰할 수 있는 소스)
        if location and 's3Location' in location:
            document_uri = location['s3Location'].get('uri', '')
        
        # 2. metadata에서 S3 URI 추출 (fallback)
        if not document_uri:
            document_uri = metadata.get('x-amz-bedrock-kb-source-uri', '')
        
        # 3. 파일명을 제목으로 사용
        if document_uri and document_uri.startswith('s3://'):
            filename = document_uri.split('/')[-1]
            if filename and '.' in filename:
                # URL 디코딩이 필요한 경우 처리
                try:
                    from urllib.parse import unquote
                    filename = unquote(filename)
                except:
                    pass
                document_title = filename
        
        # 페이지 번호 추출 (올바른 키 사용)
        page_number = metadata.get('x-amz-bedrock-kb-document-page-number')
        if page_number is not None:
            try:
                page_number = int(float(page_number))
            except (ValueError, TypeError):
                page_number = None
        
        citation = cls(
            id="",  # __post_init__에서 자동 생성
            document_uri=document_uri,
            document_title=document_title,
            chunk_text=content.get('text', ''),
            page_number=page_number,
            confidence_score=confidence_score,
            relevance_score=kb_result.get('score', 0.0),
            metadata=metadata
        )
        
        # 이미지 정보 처리
        cls._extract_images_from_kb_result(citation, kb_result)
        
        return citation
    
    @classmethod
    def _extract_images_from_kb_result(cls, citation: 'Citation', kb_result: Dict[str, Any]) -> None:
        """KB 결과에서 이미지 정보 추출"""
        metadata = kb_result.get('metadata', {})
        
        # 방법 1: 메타데이터에서 직접 이미지 URI 추출
        if 'image_uri' in metadata:
            image_uri = metadata['image_uri']
            if isinstance(image_uri, str) and image_uri.startswith('s3://'):
                image_info = ImageInfo(
                    s3_uri=image_uri,
                    alt_text=metadata.get('image_alt_text'),
                    caption=metadata.get('image_caption'),
                    image_type=cls._extract_image_type_from_uri(image_uri)
                )
                citation.add_image(image_info)
        
        # 방법 2: 메타데이터에서 이미지 배열 처리
        if 'images' in metadata:
            images_data = metadata['images']
            if isinstance(images_data, list):
                for img_data in images_data:
                    if isinstance(img_data, dict) and 's3_uri' in img_data:
                        image_info = ImageInfo(
                            s3_uri=img_data['s3_uri'],
                            alt_text=img_data.get('alt_text'),
                            caption=img_data.get('caption'),
                            width=img_data.get('width'),
                            height=img_data.get('height'),
                            file_size=img_data.get('file_size'),
                            image_type=img_data.get('image_type', 
                                cls._extract_image_type_from_uri(img_data['s3_uri']))
                        )
                        citation.add_image(image_info)
        
        # 방법 3: 소스 URI가 이미지인 경우 (전체 청크가 이미지)
        source_uri = metadata.get('source', '')
        if cls._is_image_uri(source_uri):
            image_info = ImageInfo(
                s3_uri=source_uri,
                alt_text=citation.chunk_text if citation.chunk_text else None,
                image_type=cls._extract_image_type_from_uri(source_uri)
            )
            citation.add_image(image_info)
    
    @staticmethod
    def _extract_image_type_from_uri(uri: str) -> str:
        """URI에서 이미지 타입 추출"""
        if not uri:
            return "png"
        
        # 파일 확장자에서 이미지 타입 추출
        uri_lower = uri.lower()
        if uri_lower.endswith('.png'):
            return "png"
        elif uri_lower.endswith('.jpg') or uri_lower.endswith('.jpeg'):
            return "jpg"
        elif uri_lower.endswith('.gif'):
            return "gif"
        elif uri_lower.endswith('.webp'):
            return "webp"
        elif uri_lower.endswith('.svg'):
            return "svg"
        else:
            return "png"  # 기본값
    
    @staticmethod
    def _is_image_uri(uri: str) -> bool:
        """URI가 이미지 파일인지 확인"""
        if not uri:
            return False
        
        image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg']
        uri_lower = uri.lower()
        return any(uri_lower.endswith(ext) for ext in image_extensions)


@dataclass
class CitationCollection:
    """Citation 컬렉션 관리"""
    citations: List[Citation] = field(default_factory=list)
    
    def add_citation(self, citation: Citation) -> None:
        """Citation 추가 (중복 제거)"""
        # 동일한 ID의 Citation이 있는지 확인
        existing_ids = {c.id for c in self.citations}
        if citation.id not in existing_ids:
            self.citations.append(citation)
    
    def add_citations(self, citations: List[Citation]) -> None:
        """여러 Citation 추가"""
        for citation in citations:
            self.add_citation(citation)
    
    def get_top_citations(self, n: int = 5, min_confidence: float = 0.0) -> List[Citation]:
        """상위 N개 Citation 반환 (신뢰도 기준)"""
        filtered = [c for c in self.citations if c.confidence_score >= min_confidence]
        sorted_citations = sorted(filtered, key=lambda x: x.confidence_score, reverse=True)
        return sorted_citations[:n]
    
    def remove_duplicates(self) -> None:
        """중복 Citation 제거"""
        seen_ids = set()
        unique_citations = []
        
        for citation in self.citations:
            if citation.id not in seen_ids:
                seen_ids.add(citation.id)
                unique_citations.append(citation)
        
        self.citations = unique_citations
    
    def merge_similar_citations(self, similarity_threshold: float = 0.8) -> None:
        """유사한 Citation 병합"""
        # 간단한 텍스트 유사도 기반 병합 (향후 개선 가능)
        merged = []
        processed_ids = set()
        
        for citation in self.citations:
            if citation.id in processed_ids:
                continue
            
            # 현재 Citation과 유사한 것들 찾기
            similar_citations = [citation]
            processed_ids.add(citation.id)
            
            for other in self.citations:
                if other.id in processed_ids:
                    continue
                
                # 간단한 유사도 계산 (문서 URI와 텍스트 유사도)
                if (citation.document_uri == other.document_uri and 
                    self._calculate_text_similarity(citation.chunk_text, other.chunk_text) > similarity_threshold):
                    similar_citations.append(other)
                    processed_ids.add(other.id)
            
            # 가장 높은 신뢰도의 Citation을 대표로 선택
            best_citation = max(similar_citations, key=lambda x: x.confidence_score)
            merged.append(best_citation)
        
        self.citations = merged
    
    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """간단한 텍스트 유사도 계산"""
        # Jaccard 유사도 사용
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 and not words2:
            return 1.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "citations": [c.to_dict() for c in self.citations],
            "total_count": len(self.citations)
        }
    
    def __len__(self) -> int:
        return len(self.citations)
    
    def __iter__(self):
        return iter(self.citations)


class CitationProcessor:
    """Citation 처리 유틸리티 클래스"""
    
    @staticmethod
    def process_kb_results(kb_results: List[Dict[str, Any]], 
                          rerank_scores: Optional[List[float]] = None) -> CitationCollection:
        """KB 검색 결과를 Citation으로 변환"""
        collection = CitationCollection()
        
        for i, result in enumerate(kb_results):
            confidence_score = rerank_scores[i] if rerank_scores and i < len(rerank_scores) else 0.0
            citation = Citation.from_kb_result(result, confidence_score)
            collection.add_citation(citation)
        
        # 중복 제거 및 유사한 Citation 병합
        collection.remove_duplicates()
        collection.merge_similar_citations()
        
        return collection
    
    @staticmethod
    def format_citations_for_response(citations: List[Citation], 
                                    include_preview: bool = True,
                                    max_preview_length: int = 200,
                                    include_images: bool = True) -> List[Dict[str, Any]]:
        """응답용 Citation 포맷팅 (이미지 지원 포함)"""
        formatted = []
        
        for i, citation in enumerate(citations, 1):
            formatted_citation = {
                "index": i,
                "id": citation.id,
                "title": citation.document_title,  # 실제 파일명이 포함된 title
                "document_title": citation.document_title,  # 명시적으로 추가
                "document_uri": citation.document_uri,  # 명시적으로 추가
                "uri": citation.document_uri,
                "confidence": round(citation.confidence_score, 3),
                "relevance": round(citation.relevance_score, 3),
                "content_type": citation.content_type,
                "has_images": citation.has_images(),
                "metadata": citation.metadata  # 전체 메타데이터 포함
            }
            
            if citation.page_number:
                formatted_citation["page"] = citation.page_number
                formatted_citation["page_number"] = citation.page_number  # 명시적으로 추가
            
            if include_preview and citation.chunk_text:
                formatted_citation["preview"] = citation.get_preview_text(max_preview_length)
            
            # location 정보도 포함 (원본 KB 결과 구조 유지)
            if citation.document_uri:
                formatted_citation["location"] = {
                    "s3Location": {
                        "uri": citation.document_uri
                    }
                }
            
            # 이미지 정보 포함
            if include_images and citation.has_images():
                formatted_citation["images"] = []
                for img in citation.images:
                    img_data = img.to_dict()
                    # TODO: presigned URL 생성 (향후 구현)
                    # img_data["presigned_url"] = img.get_presigned_url()
                    formatted_citation["images"].append(img_data)
                
                # 주요 이미지 정보
                primary_image = citation.get_primary_image()
                if primary_image:
                    formatted_citation["primary_image"] = primary_image.to_dict()
            
            formatted.append(formatted_citation)
        
        return formatted
    
    @staticmethod
    def generate_inline_citations(response_text: str, citations: List[Citation]) -> str:
        """응답 텍스트에 인라인 Citation 추가"""
        # 간단한 구현: 각 문장 끝에 관련 Citation 번호 추가
        # 향후 더 정교한 매핑 로직으로 개선 가능
        
        if not citations:
            return response_text
        
        # 문장 단위로 분할
        sentences = response_text.split('. ')
        
        # 각 문장에 Citation 번호 추가 (간단한 라운드로빈 방식)
        citation_count = len(citations)
        enhanced_sentences = []
        
        for i, sentence in enumerate(sentences):
            if sentence.strip():
                citation_index = (i % citation_count) + 1
                if i == len(sentences) - 1:  # 마지막 문장
                    enhanced_sentences.append(f"{sentence} [{citation_index}]")
                else:
                    enhanced_sentences.append(f"{sentence} [{citation_index}]")
        
        return '. '.join(enhanced_sentences)

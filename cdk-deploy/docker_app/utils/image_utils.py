"""
이미지 처리 유틸리티
Bedrock의 5MB 제한에 맞춰 이미지를 리사이징하는 기능 제공
"""

import io
import base64
from PIL import Image
from typing import Tuple, Optional
import math


def calculate_image_size_mb(image_data: bytes) -> float:
    """이미지 데이터의 크기를 MB 단위로 계산"""
    return len(image_data) / (1024 * 1024)


def resize_image_to_limit(image: Image.Image, max_size_mb: float = 4.8) -> Image.Image:
    """
    이미지를 지정된 크기 제한에 맞춰 리사이징
    
    Args:
        image: PIL Image 객체
        max_size_mb: 최대 크기 (MB) - 5MB보다 약간 작게 설정하여 여유 확보
    
    Returns:
        리사이징된 PIL Image 객체
    """
    # 투명도 처리 먼저 수행
    if image.mode in ('RGBA', 'LA', 'P'):
        # 투명도가 있는 경우 흰색 배경으로 변환
        background = Image.new('RGB', image.size, (255, 255, 255))
        if image.mode == 'P':
            image = image.convert('RGBA')
        background.paste(image, mask=image.split()[-1] if image.mode in ('RGBA', 'LA') else None)
        image = background
    
    # 원본 이미지 크기 확인 (JPEG 형식으로)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90, optimize=True)
    original_size_mb = calculate_image_size_mb(buffer.getvalue())
    
    print(f"원본 이미지 크기 (JPEG): {original_size_mb:.2f}MB")
    
    # 이미 제한 크기 이하면 그대로 반환
    if original_size_mb <= max_size_mb:
        buffer.seek(0)
        return Image.open(buffer)
    
    # 리사이징이 필요한 경우
    original_width, original_height = image.size
    
    # 여러 단계로 리사이징 시도
    attempts = 0
    max_attempts = 10
    current_image = image.copy()
    
    while attempts < max_attempts:
        # 리사이징 비율 계산 (면적 기준)
        scale_factor = math.sqrt(max_size_mb / original_size_mb) * 0.9  # 여유분 확보
        
        # 새로운 크기 계산
        new_width = max(200, int(original_width * scale_factor))  # 최소 200px 보장
        new_height = max(200, int(original_height * scale_factor))  # 최소 200px 보장
        
        print(f"시도 {attempts + 1}: {new_width}x{new_height} (scale: {scale_factor:.3f})")
        
        # 이미지 리사이징
        current_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # 품질을 조정하면서 크기 확인
        for quality in [90, 80, 70, 60, 50]:
            buffer = io.BytesIO()
            current_image.save(buffer, format="JPEG", quality=quality, optimize=True)
            current_size_mb = calculate_image_size_mb(buffer.getvalue())
            
            print(f"  품질 {quality}: {current_size_mb:.2f}MB")
            
            if current_size_mb <= max_size_mb:
                print(f"✅ 리사이징 성공: {new_width}x{new_height}, 품질 {quality}, {current_size_mb:.2f}MB")
                buffer.seek(0)
                return Image.open(buffer)
        
        # 크기를 더 줄여서 다시 시도
        original_size_mb = current_size_mb
        attempts += 1
    
    # 최종적으로 크기를 맞추지 못한 경우, 매우 작은 크기로 강제 리사이징
    final_width = max(200, original_width // 4)
    final_height = max(200, original_height // 4)
    final_image = image.resize((final_width, final_height), Image.Resampling.LANCZOS)
    
    buffer = io.BytesIO()
    final_image.save(buffer, format="JPEG", quality=50, optimize=True)
    buffer.seek(0)
    
    print(f"⚠️ 강제 리사이징: {final_width}x{final_height}")
    return Image.open(buffer)


def process_image_for_bedrock(uploaded_file) -> Tuple[Optional[str], Optional[Image.Image]]:
    """
    업로드된 이미지를 Bedrock에 전송할 수 있도록 처리
    
    Args:
        uploaded_file: Streamlit의 UploadedFile 객체
    
    Returns:
        Tuple[base64_encoded_string, PIL_Image_for_display]
    """
    try:
        # 이미지 열기
        image = Image.open(uploaded_file)
        
        # 5MB 제한에 맞춰 리사이징
        processed_image = resize_image_to_limit(image, max_size_mb=4.8)
        
        # Base64 인코딩을 위한 바이트 데이터 생성
        buffer = io.BytesIO()
        
        # 투명도 처리 및 최적화된 저장
        if processed_image.mode in ('RGBA', 'LA', 'P'):
            # 투명도가 있는 경우 흰색 배경으로 변환
            background = Image.new('RGB', processed_image.size, (255, 255, 255))
            if processed_image.mode == 'P':
                processed_image = processed_image.convert('RGBA')
            background.paste(processed_image, mask=processed_image.split()[-1] if processed_image.mode in ('RGBA', 'LA') else None)
            processed_image = background
        
        # JPEG 형식으로 저장 (더 작은 파일 크기)
        processed_image.save(buffer, format="JPEG", quality=90, optimize=True)
        
        # 최종 크기 확인
        final_size_mb = calculate_image_size_mb(buffer.getvalue())
        print(f"이미지 처리 완료: {final_size_mb:.2f}MB (원본 대비 압축)")
        
        # Base64 인코딩
        image_data = base64.b64encode(buffer.getvalue()).decode()
        
        # 표시용 이미지 반환 (원본 형태 유지)
        buffer.seek(0)
        display_image = Image.open(buffer)
        
        return image_data, display_image
        
    except Exception as e:
        print(f"이미지 처리 중 오류 발생: {e}")
        return None, None


def get_image_info(image: Image.Image) -> dict:
    """이미지 정보 반환"""
    buffer = io.BytesIO()
    # JPEG 형식으로 저장하여 실제 전송될 크기 측정
    if image.mode in ('RGBA', 'LA', 'P'):
        # 투명도가 있는 경우 흰색 배경으로 변환
        background = Image.new('RGB', image.size, (255, 255, 255))
        if image.mode == 'P':
            image = image.convert('RGBA')
        background.paste(image, mask=image.split()[-1] if image.mode in ('RGBA', 'LA') else None)
        image = background
    
    image.save(buffer, format="JPEG", quality=90)
    size_mb = calculate_image_size_mb(buffer.getvalue())
    
    return {
        "width": image.size[0],
        "height": image.size[1],
        "mode": image.mode,
        "format": getattr(image, 'format', 'JPEG'),
        "size_mb": round(size_mb, 2)
    }

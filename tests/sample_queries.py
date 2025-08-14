"""
KB 검색 테스트용 샘플 사용자 쿼리 (건설/건축 분야)
실제 KB 검색 테스트 시 사용할 다양한 유형의 건설/건축 관련 쿼리들
"""

# 구조 및 안전 관련 쿼리
STRUCTURAL_SAFETY_QUERIES = [
    "현장에서 기둥 상부 타설을 위해 작업발판 일체형 거푸집을 사용하려고 하고 있어 이에 대한 구조적 안정성이 확인되어야 하는지 법적 기준을 검토해줘",
    "고층 건물 시공 시 타워크레인 설치 기준과 안전 검토 사항은?",
    "지하 굴착 시 흙막이 구조물의 안전성 검토 절차를 알려줘",
    "콘크리트 타설 시 거푸집 지지력 계산 방법과 안전율 적용 기준",
    "철골 구조물 용접 시 품질 관리 기준과 검사 항목"
]

# 서류 및 관리 관련 쿼리
DOCUMENTATION_QUERIES = [
    "현장 준공이 임박함에 따라 자재 서류 중 보관이 필요한 서류 항목을 나열해줘",
    "건설공사 품질관리 계획서 작성 시 필수 포함 항목은?",
    "시공 중 발생하는 설계변경 승인 절차와 필요 서류",
    "준공검사 시 제출해야 하는 필수 서류 목록과 보관 기간",
    "하도급 계약 시 필요한 서류와 법적 요구사항"
]

# 품질관리 및 시험 관련 쿼리
QUALITY_CONTROL_QUERIES = [
    "우리는 기존 오피스텔을 철거하는 공사를 진행하고 있는데, 우리 현장에서도 품질관리 계획과 품질시험 계획을 수립해야 해?",
    "콘크리트 압축강도 시험 주기와 시료 채취 방법",
    "철근 인장시험 실시 기준과 합격 판정 기준",
    "토공사 다짐도 시험 방법과 관리 기준값",
    "방수공사 품질 검사 항목과 시험 방법"
]

# 시공 기술 및 공법 관련 쿼리
CONSTRUCTION_TECHNIQUE_QUERIES = [
    "철근 이음을 하려고 하는데 종류별 유의사항, 장/단점 등을 비교해서 정리해줘",
    "콘크리트 양생 방법별 특징과 적용 조건",
    "지하수위가 높은 지역에서의 기초 시공 방법",
    "프리캐스트 콘크리트 설치 시 주의사항과 품질 관리",
    "강관 파일 시공 시 관리 기준과 검사 항목"
]

# 자재 관리 및 품질 관련 쿼리
MATERIAL_MANAGEMENT_QUERIES = [
    "레미콘 생산업체 공장점검 시 골재 저장시설이 매우 낙후되어 있는 것을 확인했어 이에 대한 개선요청을 위해 골재 저장시설에 대한 관리기준을 한장 분량으로 정리해줘",
    "철근 현장 보관 시 품질 관리 기준과 검사 항목",
    "시멘트 보관 및 품질 관리 방법",
    "골재의 품질 기준과 시험 방법",
    "레미콘 운반 및 타설 시 품질 관리 요점"
]

# 법규 및 기준 관련 쿼리
REGULATION_QUERIES = [
    "건축법상 내화구조 적용 기준과 시공 방법",
    "건설기술진흥법에 따른 품질관리 의무사항",
    "산업안전보건법상 건설현장 안전관리 기준",
    "건설폐기물 처리 관련 법적 요구사항",
    "소음진동규제법에 따른 건설현장 소음 관리 기준"
]

# 검사 및 시험 관련 쿼리
INSPECTION_QUERIES = [
    "중간검사 시 확인해야 할 주요 검사 항목",
    "사용승인 전 최종 점검 사항과 준비 서류",
    "구조물 안전진단 실시 기준과 절차",
    "소방시설 완공검사 준비사항과 검사 항목",
    "전기설비 준공검사 시 확인 사항"
]

# 복합적 쿼리 (다중 검색이 필요한 경우)
COMPLEX_QUERIES = [
    "지하 주차장 시공 시 방수, 환기, 소방 설비 통합 관리 방안",
    "고층 아파트 시공 시 타워크레인 설치부터 철거까지 전체 안전관리 계획",
    "학교 건물 신축 시 내진설계, 친환경 인증, 장애인 편의시설 통합 적용 방법",
    "재개발 사업 시 기존 건물 철거부터 신축까지 전체 공정 관리",
    "공장 건설 시 환경영향평가, 산업안전, 소방안전 통합 검토 사항"
]

# 도면 및 시각자료 관련 쿼리 (이미지가 포함될 가능성이 높은 쿼리)
DRAWING_RELATED_QUERIES = [
    "철근 배근도 작성 시 표기 방법과 주의사항",
    "거푸집 조립도 검토 시 확인해야 할 구조적 요소",
    "배관 시공도면 검토 시 간섭 확인 방법",
    "전기 배선도 작성 기준과 안전 거리 확보 방법",
    "건축 단면도에서 층고 및 천장고 확인 방법"
]

# 모든 쿼리를 카테고리별로 정리
ALL_SAMPLE_QUERIES = {
    "structural_safety": STRUCTURAL_SAFETY_QUERIES,
    "documentation": DOCUMENTATION_QUERIES,
    "quality_control": QUALITY_CONTROL_QUERIES,
    "construction_technique": CONSTRUCTION_TECHNIQUE_QUERIES,
    "material_management": MATERIAL_MANAGEMENT_QUERIES,
    "regulation": REGULATION_QUERIES,
    "inspection": INSPECTION_QUERIES,
    "complex": COMPLEX_QUERIES,
    "drawing_related": DRAWING_RELATED_QUERIES
}

# 테스트용 간단한 쿼리들
SIMPLE_TEST_QUERIES = [
    "콘크리트 양생 방법",
    "철근 이음 종류",
    "거푸집 안전 기준",
    "품질관리 계획서",
    "준공검사 서류"
]

# 다중 검색이 필요한 복잡한 쿼리 (Orchestration Agent 테스트용)
MULTI_SEARCH_QUERIES = [
    {
        "original_query": "지하 주차장 시공 시 방수, 환기, 소방 설비 통합 관리 방안",
        "sub_queries": [
            "지하 주차장 방수공사 시공 기준",
            "지하 주차장 환기설비 설치 기준",
            "지하 주차장 소방설비 설치 요구사항",
            "지하 주차장 통합 시공 관리 방법"
        ]
    },
    {
        "original_query": "고층 아파트 시공 시 타워크레인 설치부터 철거까지 전체 안전관리 계획",
        "sub_queries": [
            "타워크레인 설치 안전 기준",
            "타워크레인 운영 중 안전관리 방법",
            "타워크레인 철거 시 안전 절차",
            "고층 건물 시공 안전관리 계획"
        ]
    },
    {
        "original_query": "재개발 사업 시 기존 건물 철거부터 신축까지 전체 공정 관리",
        "sub_queries": [
            "기존 건물 철거 공사 절차",
            "철거 후 부지 정리 및 준비 작업",
            "신축 공사 착공 준비 사항",
            "재개발 사업 전체 공정 관리 방법"
        ]
    }
]

# 실제 제공받은 테스트 쿼리들 (우선순위 높음)
PROVIDED_TEST_QUERIES = [
    "현장에서 기둥 상부 타설을 위해 작업발판 일체형 거푸집을 사용하려고 하고 있어 이에 대한 구조적 안정성이 확인되어야 하는지 법적 기준을 검토해줘",
    "현장 준공이 임박함에 따라 자재 서류 중 보관이 필요한 서류 항목을 나열해줘",
    "우리는 기존 오피스텔을 철거하는 공사를 진행하고 있는데, 우리 현장에서도 품질관리 계획과 품질시험 계획을 수립해야 해?",
    "철근 이음을 하려고 하는데 종류별 유의사항, 장/단점 등을 비교해서 정리해줘",
    "레미콘 생산업체 공장점검 시 골재 저장시설이 매우 낙후되어 있는 것을 확인했어 이에 대한 개선요청을 위해 골재 저장시설에 대한 관리기준을 한장 분량으로 정리해줘"
]


def get_sample_queries(category: str = "all", count: int = None):
    """
    카테고리별 샘플 쿼리 반환
    
    Args:
        category: 쿼리 카테고리 ("all", "provided", "structural_safety", etc.)
        count: 반환할 쿼리 수 (None이면 전체)
    
    Returns:
        선택된 쿼리 리스트
    """
    if category == "provided":
        queries = PROVIDED_TEST_QUERIES
    elif category == "all":
        all_queries = []
        for queries_list in ALL_SAMPLE_QUERIES.values():
            all_queries.extend(queries_list)
        queries = all_queries
    elif category in ALL_SAMPLE_QUERIES:
        queries = ALL_SAMPLE_QUERIES[category]
    else:
        queries = SIMPLE_TEST_QUERIES
    
    if count and count < len(queries):
        return queries[:count]
    
    return queries


def get_multi_search_query(index: int = 0):
    """
    다중 검색 테스트용 쿼리 반환
    
    Args:
        index: 쿼리 인덱스 (0-2)
    
    Returns:
        {"original_query": str, "sub_queries": List[str]}
    """
    if 0 <= index < len(MULTI_SEARCH_QUERIES):
        return MULTI_SEARCH_QUERIES[index]
    else:
        return MULTI_SEARCH_QUERIES[0]


def get_provided_test_queries():
    """실제 제공받은 테스트 쿼리들 반환 (우선 테스트용)"""
    return PROVIDED_TEST_QUERIES.copy()


if __name__ == "__main__":
    # 샘플 쿼리 출력 예시
    print("=== 실제 제공받은 테스트 쿼리 ===")
    for i, query in enumerate(get_provided_test_queries(), 1):
        print(f"{i}. {query[:50]}...")
    
    print("\n=== 구조 안전 관련 쿼리 예시 ===")
    for i, query in enumerate(get_sample_queries("structural_safety", 3), 1):
        print(f"  {i}. {query[:50]}...")
    
    print("\n=== 복합 쿼리 예시 ===")
    multi_query = get_multi_search_query(0)
    print(f"원본 쿼리: {multi_query['original_query'][:50]}...")
    print("세부 쿼리:")
    for i, sub_query in enumerate(multi_query['sub_queries'], 1):
        print(f"  {i}. {sub_query}")

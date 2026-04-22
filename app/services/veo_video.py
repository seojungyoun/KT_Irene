import vertexai
from vertexai.preview.generative_models import GenerativeModel
import os

def generate_video_content(prompt: str, output_file: str):
    # 1. 초기화 (본인의 프로젝트 ID로 꼭 변경하세요!)
    vertexai.init(project="kt-irene", location="us-central1")
    
    # 2. Veo 모델 선언
    model = GenerativeModel("veo-001")
    
    try:
        # 3. 영상 생성 요청
        response = model.generate_content(prompt)
        
        # [수정 포인트] response 객체 내부의 실제 비디오 데이터를 가져오는 올바른 방법
        # 보통 Veo의 응답 파트(Part) 중 inline_data나 file_uri에 데이터가 담깁니다.
        # 최신 SDK 기준으로는 아래와 같이 접근합니다.
        video_part = response.candidates[0].content.parts[0]
        
        if video_part.inline_data:
            video_data = video_part.inline_data.data
            with open(output_file, "wb") as f:
                f.write(video_data)
            return output_file
        else:
            print("응답에 비디오 데이터가 포함되어 있지 않습니다.")
            return None

    except Exception as e:
        print(f"영상 생성 중 에러 발생: {e}")
        return None
import vertexai
from vertexai.preview.generative_models import GenerativeModel
import os

# [여기를 본인의 프로젝트 ID로 꼭 수정하세요]
MY_PROJECT_ID = "kt-irene" 

def init_veo():
    # 전역 변수 MY_PROJECT_ID를 사용하여 초기화합니다.
    vertexai.init(project=MY_PROJECT_ID, location="us-central1")

async def generate_veo_video(prompt_text: str, output_path: str):
    """
    텍스트를 받아 영상을 생성하고 지정된 경로에 저장합니다.
    """
    try:
        # 1. API 초기화 호출
        init_veo()
        
        # 2. 모델 설정 (Veo 3 모델명 확인 필수)
        model = GenerativeModel("veo-001") 
        
        # 3. 영상 생성 요청
        full_prompt = f"Cinematic high quality video of: {prompt_text}"
        response = model.generate_content(full_prompt)
        
        # 4. 데이터 추출 및 파일 저장 (AttributeError 방지 로직)
        # response -> candidates -> content -> parts 순으로 접근합니다.
        video_part = response.candidates[0].content.parts[0]
        
        if hasattr(video_part, 'inline_data') and video_part.inline_data:
            with open(output_path, "wb") as f:
                f.write(video_part.inline_data.data)
            return output_path
        elif hasattr(video_part, 'file_uri'):
            # GCS에 저장된 경우 (환경에 따라 다를 수 있음)
            print(f"영상 저장 위치: {video_part.file_uri}")
            return video_part.file_uri
            
        print("비디오 데이터를 찾을 수 없습니다.")
        return None

    except Exception as e:
        print(f"Veo 실행 에러: {str(e)}")
        return None
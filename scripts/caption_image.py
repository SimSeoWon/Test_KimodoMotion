#!/usr/bin/env python3
"""이미지 -> 짧은 캡션(동작 프롬프트 초안). 로컬 BLIP 모델(CPU 전용, GPU는 kimodo용으로 비워둠).

최초 1회만 Hugging Face Hub에서 가중치(~1GB)를 받고(인터넷 필요), 그 뒤로는 로컬 캐시로
완전히 오프라인 동작한다. BLIP은 COCO류 캡션 데이터로 학습돼 있어서 "a person jumping in
the air" 식으로 원래 짧고 직접적으로 나오는 편이라 Kimodo가 원하는 프롬프트 스타일과
잘 맞는다(사진/영화 촬영 묘사처럼 장황하게 안 나옴 — history/2026-09-17 참고).

사용법:
    py scripts\\caption_image.py <이미지 경로>
"""
import sys
from pathlib import Path


def main():
    if len(sys.argv) != 2:
        print("usage: caption_image.py <image_path>", file=sys.stderr)
        sys.exit(2)
    image_path = Path(sys.argv[1])
    if not image_path.exists():
        print(f"이미지를 찾을 수 없습니다: {image_path}", file=sys.stderr)
        sys.exit(1)

    from PIL import Image
    from transformers import BlipProcessor, BlipForConditionalGeneration

    model_name = "Salesforce/blip-image-captioning-base"
    processor = BlipProcessor.from_pretrained(model_name)
    model = BlipForConditionalGeneration.from_pretrained(model_name)

    image = Image.open(image_path).convert("RGB")
    inputs = processor(image, return_tensors="pt")
    out = model.generate(**inputs, max_new_tokens=30)
    caption = processor.decode(out[0], skip_special_tokens=True).strip()
    print(caption)


if __name__ == "__main__":
    main()

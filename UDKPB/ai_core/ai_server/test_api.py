"""
Small smoke-test script for the AI server endpoints.
"""
import json
import os
from pathlib import Path

import requests


def post_images(url, image_paths):
    files = []
    try:
        for path in image_paths:
            if os.path.exists(path):
                files.append(("images", (os.path.basename(path), open(path, "rb"), "image/jpeg")))

        if not files:
            print("No images to test.")
            return None

        response = requests.post(url, files=files, timeout=300)
        print(f"Status Code: {response.status_code}")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
        return response.status_code == 200
    finally:
        for _field, file_tuple in files:
            file_tuple[1].close()


def test_health_check(base_url):
    print("\nTEST 1: Health Check")
    response = requests.get(f"{base_url}/api/health/", timeout=30)
    print(f"Status Code: {response.status_code}")
    print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    return response.status_code == 200


def test_model_info(base_url):
    print("\nTEST 2: Model Info")
    response = requests.get(f"{base_url}/api/info/", timeout=30)
    print(f"Status Code: {response.status_code}")
    print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    return response.status_code == 200


def test_vietnameocr_recognize(base_url, image_paths):
    print("\nTEST 3: model_vietnameocr Recognize")
    return post_images(f"{base_url}/api/model_vietnameocr/recognize/", image_paths)


def test_resnet18_x_detect(base_url, image_paths):
    print("\nTEST 4: model_resnet18_x Detect")
    return post_images(f"{base_url}/api/model_resnet18_x/detect/", image_paths)


def test_resnet18_crossed_detect(base_url, image_paths):
    print("\nTEST 5: model_resnet18_crossed Detect")
    return post_images(f"{base_url}/api/model_resnet18_crossed/detect/", image_paths)


def main():
    base_url = "http://localhost:8081"
    print(f"AI server API tests: {base_url}")

    test1 = test_health_check(base_url)
    test2 = test_model_info(base_url)

    project_root = Path(__file__).resolve().parents[2]
    static_ballot_dir = project_root / "kiem_phieu_bau" / "static" / "ballot"
    sample_images = [str(path) for path in static_ballot_dir.glob("*.jpg")][:2]

    test3 = test_vietnameocr_recognize(base_url, sample_images) if sample_images else None
    test4 = test_resnet18_x_detect(base_url, sample_images) if sample_images else None
    test5 = test_resnet18_crossed_detect(base_url, sample_images) if sample_images else None

    print("\nTEST SUMMARY")
    print(f"Health Check: {'PASS' if test1 else 'FAIL'}")
    print(f"Model Info: {'PASS' if test2 else 'FAIL'}")
    print(f"model_vietnameocr: {'PASS' if test3 else 'SKIPPED' if test3 is None else 'FAIL'}")
    print(f"model_resnet18_x: {'PASS' if test4 else 'SKIPPED' if test4 is None else 'FAIL'}")
    print(f"model_resnet18_crossed: {'PASS' if test5 else 'SKIPPED' if test5 is None else 'FAIL'}")


if __name__ == "__main__":
    main()

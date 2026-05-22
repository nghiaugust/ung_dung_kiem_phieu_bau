"""
Small smoke-test script for the AI server API.
"""
import json
import os
from pathlib import Path

import requests


def test_health_check(base_url):
    print("\n" + "=" * 60)
    print("TEST 1: Health Check")
    print("=" * 60)

    response = requests.get(f"{base_url}/api/health/")
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    return response.status_code == 200


def test_model_info(base_url):
    print("\n" + "=" * 60)
    print("TEST 2: Model Info")
    print("=" * 60)

    response = requests.get(f"{base_url}/api/info/")
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    return response.status_code == 200


def test_vietnameocr_recognize(base_url, image_paths):
    print("\n" + "=" * 60)
    print("TEST 3: VietNameOCR Recognize")
    print("=" * 60)

    files = []
    for path in image_paths:
        if os.path.exists(path):
            files.append(("images", open(path, "rb")))
            print(f"Added: {os.path.basename(path)}")
        else:
            print(f"Not found: {path}")

    if not files:
        print("No images to test.")
        return False

    try:
        response = requests.post(f"{base_url}/api/vietnameocr/recognize/", files=files)
    finally:
        for _, file in files:
            file.close()

    print(f"\nStatus Code: {response.status_code}")

    if response.status_code == 200:
        result = response.json()
        print(f"Success: {result['success']}")
        print(f"Count: {result['count']}")
        print("\nResults:")
        for row in result["results"]:
            print(f"  - {row['filename']}: {row['text']} ({row['status']})")
    else:
        print(f"Error: {response.text}")

    return response.status_code == 200


def test_yolo_detect(base_url, image_paths):
    print("\n" + "=" * 60)
    print("TEST 4: YOLO Detect")
    print("=" * 60)

    files = []
    for path in image_paths:
        if os.path.exists(path):
            files.append(("images", open(path, "rb")))
            print(f"Added: {os.path.basename(path)}")
        else:
            print(f"Not found: {path}")

    if not files:
        print("No images to test.")
        return False

    try:
        response = requests.post(f"{base_url}/api/yolo/detect/", files=files)
    finally:
        for _, file in files:
            file.close()

    print(f"\nStatus Code: {response.status_code}")

    if response.status_code == 200:
        result = response.json()
        print(f"Success: {result['success']}")
        print(f"Count: {result['count']}")
        print("\nResults:")
        for row in result["results"]:
            print(
                f"  - {row['filename']}: {row['label']} "
                f"({len(row['detections'])} detections, {row['status']})"
            )
            for detection in row["detections"]:
                print(f"      - {detection['class']}: {detection['confidence']:.2f}")
    else:
        print(f"Error: {response.text}")

    return response.status_code == 200


def main():
    base_url = "http://localhost:8081"

    print("\n" + "=" * 60)
    print("AI SERVER API TEST SUITE")
    print("=" * 60)
    print(f"Base URL: {base_url}")

    test1 = test_health_check(base_url)
    test2 = test_model_info(base_url)

    test_dir = (
        Path(__file__).parent.parent.parent
        / "ballot_processing_system"
        / "ket_qua_tien_xu_ly_v2"
    )
    vietnameocr_images = []
    if test_dir.exists():
        vietnameocr_images = [str(path) for path in test_dir.glob("*hoten*.jpg")][:3]

    if vietnameocr_images:
        test3 = test_vietnameocr_recognize(base_url, vietnameocr_images)
    else:
        print(f"\nNo images found for VietNameOCR test. Directory: {test_dir}")
        test3 = None

    ballot_dir = (
        Path(__file__).parent.parent.parent
        / "ballot_processing_system"
        / "ballot"
        / "data1"
    )
    yolo_images = []
    if ballot_dir.exists():
        yolo_images = [str(path) for path in ballot_dir.glob("*.jpg")][:2]

    if yolo_images:
        test4 = test_yolo_detect(base_url, yolo_images)
    else:
        print(f"\nNo images found for YOLO test. Directory: {ballot_dir}")
        test4 = None

    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Test 1 (Health Check): {'PASS' if test1 else 'FAIL'}")
    print(f"Test 2 (Model Info): {'PASS' if test2 else 'FAIL'}")
    print(f"Test 3 (VietNameOCR): {'PASS' if test3 else 'FAIL' if test3 is not None else 'SKIPPED'}")
    print(f"Test 4 (YOLO): {'PASS' if test4 else 'FAIL' if test4 is not None else 'SKIPPED'}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as exc:
        print(f"\nError: {exc}")
        import traceback

        traceback.print_exc()

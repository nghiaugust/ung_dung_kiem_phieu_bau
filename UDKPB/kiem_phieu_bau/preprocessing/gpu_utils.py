"""
GPU Utilities cho xử lý ảnh với OpenCV CUDA
Tự động fallback về CPU nếu GPU không khả dụng
"""
import cv2
import numpy as np

# Kiểm tra GPU có sẵn không
_GPU_AVAILABLE = False
_GPU_CHECKED = False

def check_gpu_available():
    """
    Kiểm tra xem OpenCV có được build với CUDA support không
    
    Returns:
        bool: True nếu GPU khả dụng, False nếu không
    """
    global _GPU_AVAILABLE, _GPU_CHECKED
    
    if _GPU_CHECKED:
        return _GPU_AVAILABLE
    
    try:
        # Kiểm tra CUDA device count
        count = cv2.cuda.getCudaEnabledDeviceCount()
        if count > 0:
            _GPU_AVAILABLE = True
            print(f"[GPU] ✓ Phát hiện {count} CUDA device(s)")
            
            # In thông tin GPU
            for i in range(count):
                device_info = cv2.cuda.getDevice()
                print(f"[GPU] Device {i}: CUDA compute capability")
        else:
            _GPU_AVAILABLE = False
            print("[GPU] ✗ Không phát hiện CUDA device")
    except Exception as e:
        _GPU_AVAILABLE = False
        print(f"[GPU] ✗ OpenCV không được build với CUDA support: {e}")
        print("[GPU] Sử dụng CPU fallback")
    
    _GPU_CHECKED = True
    return _GPU_AVAILABLE


def gpu_resize(img, dsize, interpolation=cv2.INTER_CUBIC):
    """
    Resize ảnh sử dụng GPU nếu có, fallback CPU nếu không
    
    Args:
        img: numpy array - Ảnh đầu vào
        dsize: tuple (width, height) - Kích thước đầu ra
        interpolation: int - Phương pháp interpolation
        
    Returns:
        numpy array: Ảnh đã resize
    """
    if check_gpu_available():
        try:
            # Upload lên GPU
            gpu_img = cv2.cuda_GpuMat()
            gpu_img.upload(img)
            
            # Resize trên GPU
            gpu_resized = cv2.cuda.resize(gpu_img, dsize, interpolation=interpolation)
            
            # Download về CPU
            result = gpu_resized.download()
            
            # Cleanup GPU memory
            del gpu_img, gpu_resized
            
            return result
        except Exception as e:
            print(f"[GPU WARNING] Resize failed, fallback to CPU: {e}")
    
    # CPU fallback
    return cv2.resize(img, dsize, interpolation=interpolation)


def gpu_warp_perspective(img, M, dsize):
    """
    Warp perspective sử dụng GPU nếu có, fallback CPU nếu không
    
    Args:
        img: numpy array - Ảnh đầu vào
        M: numpy array - Ma trận perspective transform (3x3)
        dsize: tuple (width, height) - Kích thước đầu ra
        
    Returns:
        numpy array: Ảnh đã warp
    """
    if check_gpu_available():
        try:
            # Upload lên GPU
            gpu_img = cv2.cuda_GpuMat()
            gpu_img.upload(img)
            
            # Warp perspective trên GPU
            gpu_warped = cv2.cuda.warpPerspective(gpu_img, M, dsize)
            
            # Download về CPU
            result = gpu_warped.download()
            
            # Cleanup GPU memory
            del gpu_img, gpu_warped
            
            return result
        except Exception as e:
            print(f"[GPU WARNING] WarpPerspective failed, fallback to CPU: {e}")
    
    # CPU fallback
    return cv2.warpPerspective(img, M, dsize)


def gpu_cvt_color(img, code):
    """
    Convert color space sử dụng GPU nếu có, fallback CPU nếu không
    
    Args:
        img: numpy array - Ảnh đầu vào
        code: int - Color conversion code (cv2.COLOR_*)
        
    Returns:
        numpy array: Ảnh đã convert
    """
    if check_gpu_available():
        try:
            # Upload lên GPU
            gpu_img = cv2.cuda_GpuMat()
            gpu_img.upload(img)
            
            # Convert color trên GPU
            gpu_converted = cv2.cuda.cvtColor(gpu_img, code)
            
            # Download về CPU
            result = gpu_converted.download()
            
            # Cleanup GPU memory
            del gpu_img, gpu_converted
            
            return result
        except Exception as e:
            print(f"[GPU WARNING] CvtColor failed, fallback to CPU: {e}")
    
    # CPU fallback
    return cv2.cvtColor(img, code)


def gpu_gaussian_blur(img, ksize, sigmaX):
    """
    Gaussian blur sử dụng GPU nếu có, fallback CPU nếu không
    
    Args:
        img: numpy array - Ảnh đầu vào
        ksize: tuple (width, height) - Kernel size
        sigmaX: float - Gaussian kernel standard deviation in X direction
        
    Returns:
        numpy array: Ảnh đã blur
    """
    if check_gpu_available():
        try:
            # Upload lên GPU
            gpu_img = cv2.cuda_GpuMat()
            gpu_img.upload(img)
            
            # Create Gaussian filter
            gaussian_filter = cv2.cuda.createGaussianFilter(
                gpu_img.type(), -1, ksize, sigmaX
            )
            
            # Apply filter
            gpu_blurred = gaussian_filter.apply(gpu_img)
            
            # Download về CPU
            result = gpu_blurred.download()
            
            # Cleanup GPU memory
            del gpu_img, gpu_blurred, gaussian_filter
            
            return result
        except Exception as e:
            print(f"[GPU WARNING] GaussianBlur failed, fallback to CPU: {e}")
    
    # CPU fallback
    return cv2.GaussianBlur(img, ksize, sigmaX)


def gpu_canny(img, low_threshold, high_threshold):
    """
    Canny edge detection sử dụng GPU nếu có, fallback CPU nếu không
    
    Args:
        img: numpy array - Ảnh grayscale đầu vào
        low_threshold: float - Low threshold for edge linking
        high_threshold: float - High threshold for edge linking
        
    Returns:
        numpy array: Edge map
    """
    if check_gpu_available():
        try:
            # Upload lên GPU
            gpu_img = cv2.cuda_GpuMat()
            gpu_img.upload(img)
            
            # Create Canny edge detector
            canny_detector = cv2.cuda.createCannyEdgeDetector(
                low_threshold, high_threshold
            )
            
            # Detect edges
            gpu_edges = canny_detector.detect(gpu_img)
            
            # Download về CPU
            result = gpu_edges.download()
            
            # Cleanup GPU memory
            del gpu_img, gpu_edges, canny_detector
            
            return result
        except Exception as e:
            print(f"[GPU WARNING] Canny failed, fallback to CPU: {e}")
    
    # CPU fallback
    return cv2.Canny(img, low_threshold, high_threshold)


def gpu_threshold(img, thresh, maxval, type):
    """
    Threshold sử dụng GPU nếu có, fallback CPU nếu không
    
    Args:
        img: numpy array - Ảnh đầu vào
        thresh: float - Threshold value
        maxval: float - Maximum value
        type: int - Thresholding type
        
    Returns:
        tuple: (retval, thresholded_image)
    """
    if check_gpu_available():
        try:
            # Upload lên GPU
            gpu_img = cv2.cuda_GpuMat()
            gpu_img.upload(img)
            
            # Threshold trên GPU
            _, gpu_thresholded = cv2.cuda.threshold(gpu_img, thresh, maxval, type)
            
            # Download về CPU
            result = gpu_thresholded.download()
            
            # Cleanup GPU memory
            del gpu_img, gpu_thresholded
            
            return (thresh, result)
        except Exception as e:
            print(f"[GPU WARNING] Threshold failed, fallback to CPU: {e}")
    
    # CPU fallback
    return cv2.threshold(img, thresh, maxval, type)


def gpu_filter2d(img, ddepth, kernel):
    """
    Filter2D (convolution) sử dụng GPU nếu có, fallback CPU nếu không
    
    Args:
        img: numpy array - Ảnh đầu vào
        ddepth: int - Desired depth of destination image
        kernel: numpy array - Convolution kernel
        
    Returns:
        numpy array: Filtered image
    """
    if check_gpu_available():
        try:
            # Upload lên GPU
            gpu_img = cv2.cuda_GpuMat()
            gpu_img.upload(img)
            
            # Create linear filter
            linear_filter = cv2.cuda.createLinearFilter(
                gpu_img.type(), ddepth, kernel
            )
            
            # Apply filter
            gpu_filtered = linear_filter.apply(gpu_img)
            
            # Download về CPU
            result = gpu_filtered.download()
            
            # Cleanup GPU memory
            del gpu_img, gpu_filtered, linear_filter
            
            return result
        except Exception as e:
            print(f"[GPU WARNING] Filter2D failed, fallback to CPU: {e}")
    
    # CPU fallback
    return cv2.filter2D(img, ddepth, kernel)


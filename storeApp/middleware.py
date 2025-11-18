"""
Middleware để xử lý Accept-Language header từ frontend
và activate locale tương ứng trong Django

I18N DISABLED - Tạm thời tắt đa ngôn ngữ để refactor
Để bật lại: uncomment code trong process_request và process_response
"""
from django.utils import translation
from django.utils.deprecation import MiddlewareMixin


class LocaleMiddleware(MiddlewareMixin):
    """
    Middleware để xử lý Accept-Language header và activate locale
    
    I18N DISABLED - Tạm thời luôn dùng locale 'vi'
    """
    def process_request(self, request):
        # I18N DISABLED - Tạm thời luôn dùng 'vi'
        # Để bật lại: uncomment code bên dưới và comment dòng translation.activate('vi')
        
        # # Lấy locale từ Accept-Language header
        # accept_language = request.META.get('HTTP_ACCEPT_LANGUAGE', 'vi')
        # 
        # # Parse locale (có thể là 'vi', 'en', 'vi-VN', 'en-US', etc.)
        # # Chỉ lấy 2 ký tự đầu (vi, en)
        # locale = accept_language.split('-')[0].split(',')[0].strip().lower()
        # 
        # # Validate locale (chỉ hỗ trợ vi và en)
        # if locale not in ['vi', 'en']:
        #     locale = 'vi'  # Default to Vietnamese
        # 
        # # Activate locale
        # translation.activate(locale)
        # request.LANGUAGE_CODE = locale
        
        # Tạm thời: luôn dùng 'vi'
        translation.activate('vi')
        request.LANGUAGE_CODE = 'vi'
        
        return None
    
    def process_response(self, request, response):
        # Deactivate locale sau khi xử lý request
        translation.deactivate()
        return response



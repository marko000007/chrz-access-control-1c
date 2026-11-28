"""Не допускает сохранение личных страниц проходной в HTTP-кеше."""
from django.utils.cache import patch_cache_control,patch_vary_headers


class PrivatePagesMiddleware:
    def __init__(self,get_response):self.get_response=get_response

    def __call__(self,request):
        private=request.user.is_authenticated or request.path.startswith('/accounts/')
        response=self.get_response(request)
        if private:
            patch_cache_control(response,private=True,no_store=True,no_cache=True,max_age=0,must_revalidate=True)
            patch_vary_headers(response,['Cookie'])
        return response

from rest_framework.pagination import PageNumberPagination


class BasePagination(PageNumberPagination):
    page_size = 6


class MedicineUnitPagination(PageNumberPagination):
    page_size = 9


class ExaminationPaginator(PageNumberPagination):
    page_size = 30


class PrescribingPaginator(PageNumberPagination):
    page_size = 10  # Set the default page size to 10
    page_size_query_param = 'page_size'
    max_page_size = 100
from rest_framework.serializers import ModelSerializer

from mainApp import cloud_context
from mainApp.models import Medicine, Category, MedicineUnit
from rest_framework import serializers

from mainApp.serializers.category import CategorySerializer
from mainApp.serializers.medicine import MedicineSerializer


class MedicineUnitSerializer(ModelSerializer):
    image_path = serializers.SerializerMethodField(source='image')
    medicine = serializers.PrimaryKeyRelatedField(queryset=Medicine.objects.all())
    category = serializers.PrimaryKeyRelatedField(queryset=Category.objects.all())

    class Meta:
        model = MedicineUnit
        fields = ["id", "price", "in_stock", "image", "packaging", "medicine", "category", "image_path"]
        extra_kwargs = {
            'image_path': {'read_only': 'true'},
            'image': {'write_only': 'true'},
        }

    def get_image_path(self, obj):
        if obj.image:
            path = '{cloud_context}{image_name}'.format(cloud_context=cloud_context, image_name=obj.image)
            return path

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['medicine'] = MedicineSerializer(instance.medicine).data
        representation['category'] = CategorySerializer(instance.category).data
        return representation
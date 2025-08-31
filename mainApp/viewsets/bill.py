import hashlib
import hmac
import json
import os
import urllib
import uuid
import requests
from datetime import datetime, time
from random import random

from django.http.response import HttpResponseRedirect
from rest_framework.decorators import action
from rest_framework import viewsets, generics

from mainApp.constant import SERVICE_FEE_PER_PRESCRIBING
from mainApp.models import Bill, Prescribing

from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework import status

from mainApp.serializers import BillSerializer


class BillViewSet(viewsets.ViewSet, generics.CreateAPIView,
                  generics.DestroyAPIView, generics.RetrieveAPIView,
                  generics.UpdateAPIView, generics.ListAPIView):
    queryset = Bill.objects.filter(active=True)
    serializer_class = BillSerializer
    parser_classes = [JSONParser, MultiPartParser]

    def get_parsers(self):
        return super().get_parsers()

    @action(methods=['POST'], detail=False, url_path='get-bill-by-pres')
    def get_bill_by_pres(self, request):
        user = request.user
        if user:
            try:
                prescribing = request.data.get('prescribing')
            except:
                return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            if prescribing:
                try:
                    bill = Bill.objects.get(prescribing=prescribing)
                except:
                    return Response(data=[],
                                    status=status.HTTP_500_INTERNAL_SERVER_ERROR)

                return Response(BillSerializer(bill, context={'request': request}).data,
                                status=status.HTTP_200_OK)
            return Response(status=status.HTTP_400_BAD_REQUEST)
        return Response(data={"errMgs": "User not found"},
                        status=status.HTTP_400_BAD_REQUEST)

    @action(methods=['GET'], detail=False, url_path='bill_status')
    def get_bill_status(self, request):
        try:
            diagnosis_id = request.GET.get('diagnosisId')
            prescribing_id = request.GET.get('prescribingId')
            
            if diagnosis_id:
                from mainApp.models import Diagnosis, Prescribing
                try:
                    diagnosis = Diagnosis.objects.get(id=int(diagnosis_id))
                    prescribing_list = Prescribing.objects.filter(diagnosis=diagnosis, active=True)
                    
     
                    if request.GET['resultCode'] != str(0):
                        return HttpResponseRedirect(redirect_to=os.getenv('CLIENT_SERVER')+'/dashboard/prescribing/' + str(diagnosis_id) + '/payments')
                    else:
                        from mainApp.models import PrescriptionDetail
                        total_medicine_cost = 0
                        
                        for prescribing in prescribing_list:
                            prescription_details = PrescriptionDetail.objects.filter(
                                prescribing=prescribing, 
                                active=True
                            )
                            
                            medicine_cost = 0
                            for detail in prescription_details:
                                medicine_cost += detail.medicine_unit.price * detail.quantity
                            
                            total_medicine_cost += medicine_cost
                        
                        service_fee_per_prescribing = SERVICE_FEE_PER_PRESCRIBING / len(prescribing_list) if len(prescribing_list) > 0 else 0
                        
                        for prescribing in prescribing_list:
                            if not Bill.objects.filter(prescribing=prescribing).exists():
                                prescription_details = PrescriptionDetail.objects.filter(
                                    prescribing=prescribing, 
                                    active=True
                                )
                                
                                medicine_cost = 0
                                for detail in prescription_details:
                                    medicine_cost += detail.medicine_unit.price * detail.quantity
                                
                                total_amount = medicine_cost + service_fee_per_prescribing
                                
                                Bill.objects.create(
                                    prescribing=prescribing, 
                                    amount=total_amount
                                )
                        
                        return HttpResponseRedirect(redirect_to=os.getenv('CLIENT_SERVER')+'/dashboard/prescribing/' + str(diagnosis_id) + '/payments')
                        
                except (Diagnosis.DoesNotExist, ValueError) as e:
                    print(f"Error processing diagnosis payment: {str(e)}")
                    return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                    data={'errMsg': 'Diagnosis not found or invalid data'})
                    
            elif prescribing_id:
                try:
                    prescribing = Prescribing.objects.get(id=int(prescribing_id))
                    
                    if request.GET['resultCode'] != str(0):
                        return HttpResponseRedirect(redirect_to=os.getenv('CLIENT_SERVER')+'/dashboard/prescribing/' + str(prescribing.diagnosis.id) + '/payments')
                    else:
                        prescription_details = PrescriptionDetail.objects.filter(
                            prescribing=prescribing, 
                            active=True
                        )
                        
                        medicine_cost = 0
                        for detail in prescription_details:
                            medicine_cost += detail.medicine_unit.price * detail.quantity
                        
                        total_amount = medicine_cost + SERVICE_FEE_PER_PRESCRIBING
                        
                        if not Bill.objects.filter(prescribing=prescribing).exists():
                            Bill.objects.create(prescribing=prescribing, amount=total_amount)
                        
                        return HttpResponseRedirect(redirect_to=os.getenv('CLIENT_SERVER')+'/dashboard/prescribing/' + str(prescribing.diagnosis.id) + '/payments')
                            
                except Prescribing.DoesNotExist:
                    return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                    data={'errMsg': 'Prescribing not found'})
            else:
                return Response(status=status.HTTP_400_BAD_REQUEST,
                                data={'errMsg': 'Either diagnosisId or prescribingId is required'})

        except Exception as e:
            print(f"Error in get_bill_status: {str(e)}")
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            data={'errMsg': 'Internal server error'})

    @action(methods=['POST'], detail=False, url_path='momo-payments')
    def momo_payments(self, request):
        try:
            diagnosis_id = request.data.get('diagnosisID')
            
            if not diagnosis_id:
                return Response(
                    data={'errMsg': 'diagnosisID is required'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            from mainApp.models import Diagnosis, Prescribing
            try:
                diagnosis = Diagnosis.objects.get(id=diagnosis_id)
                prescribing_list = Prescribing.objects.filter(diagnosis=diagnosis, active=True)
                
                if not prescribing_list.exists():
                    return Response(
                        data={'errMsg': 'No prescribing found for this diagnosis'}, 
                        status=status.HTTP_404_NOT_FOUND
                    )
                    
            except Diagnosis.DoesNotExist:
                return Response(
                    data={'errMsg': 'Diagnosis not found'}, 
                    status=status.HTTP_404_NOT_FOUND
                )
            
            from mainApp.models import PrescriptionDetail
            total_medicine_cost = 0
            
            for prescribing in prescribing_list:
                prescription_details = PrescriptionDetail.objects.filter(
                    prescribing=prescribing, 
                    active=True
                )
                
                medicine_cost = 0
                for detail in prescription_details:
                    medicine_cost += detail.medicine_unit.price * detail.quantity
                
                total_medicine_cost += medicine_cost
            
            total_amount = total_medicine_cost + SERVICE_FEE_PER_PRESCRIBING
            
            prescribing_ids = list(prescribing_list.values_list('id', flat=True))
            
            endpoint = "https://test-payment.momo.vn/v2/gateway/api/create"
            partnerCode = os.getenv('MOMO_PARTNER_CODE')
            accessKey = os.getenv('MOMO_ACCESS_KEY')
            secretKey = os.getenv('MOMO_SECRET_KEY')
            orderInfo = f"DiagnosisID: {diagnosis_id} - #PrescribingIDs: {prescribing_ids}"
            
            # Redirect Server URL
            redirectUrl = os.getenv('SERVER') + f"/bills/bill_status?diagnosisId={diagnosis_id}"
            # Redirect Client URL
            ipnUrl = os.getenv('CLIENT_SERVER') + "/dashboard/prescribing/" + str(diagnosis_id) + "/payments/"
            amount = str(int(total_amount))
            orderId = str(uuid.uuid4())
            requestId = str(uuid.uuid4())
            requestType = "captureWallet"
            # extraData = json.dumps({"diagnosis_id": diagnosis_id, "prescribing_ids": prescribing_ids})
            extraData = ""

            # before sign HMAC SHA256 with format: accessKey=$accessKey&amount=$amount&extraData=$extraData&ipnUrl=$ipnUrl
            # &orderId=$orderId&orderInfo=$orderInfo&partnerCode=$partnerCode&redirectUrl=$redirectUrl&requestId=$requestId
            # &requestType=$requestType
            rawSignature = "accessKey=" + accessKey + "&amount=" + amount + "&extraData=" + extraData + "&ipnUrl=" + ipnUrl + "&orderId=" + orderId + "&orderInfo=" + orderInfo + "&partnerCode=" + partnerCode + "&redirectUrl=" + redirectUrl + "&requestId=" + requestId + "&requestType=" + requestType

            # puts raw signature
            print("--------------------RAW SIGNATURE----------------")
            print(rawSignature)
            # signature
            h = hmac.new(bytes(secretKey, 'ascii'), bytes(rawSignature, 'ascii'), hashlib.sha256)
            signature = h.hexdigest()
            print("--------------------SIGNATURE----------------")
            print(signature)

            # json object send to MoMo endpoint
            data = {
                'partnerCode': partnerCode,
                'partnerName': "Test",
                'storeId': "MomoTestStore",
                'requestId': requestId,
                'amount': amount,
                'orderId': orderId,
                'orderInfo': orderInfo,
                'redirectUrl': redirectUrl,
                'ipnUrl': ipnUrl,
                'lang': "vi",
                'extraData': extraData,
                'requestType': requestType,
                'signature': signature
            }
            print("--------------------JSON REQUEST----------------\n")
            data = json.dumps(data)
            print(data)

            clen = len(data)
            response = requests.post(endpoint, data=data,
                                     headers={'Content-Type': 'application/json', 'Content-Length': str(clen)})

            print("--------------------JSON response----------------\n")
            response_data = response.json()
            print(response_data)

            user = request.user
            if user:
                # Kiểm tra xem response có thành công không
                if response_data.get('resultCode') == 0:
                    return Response(data={"payUrl": response_data['payUrl']}, status=status.HTTP_200_OK)
                else:
                    return Response(
                        data={'errMsg': f"MoMo payment failed: {response_data.get('message', 'Unknown error')}"}, 
                        status=status.HTTP_400_BAD_REQUEST
                    )

            return Response(data={'errMsg': "User not found"},
                            status=status.HTTP_400_BAD_REQUEST)
                            
        except Exception as e:
            print(f"Error in momo_payments: {str(e)}")
            return Response(
                data={'errMsg': 'Internal server error'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(methods=['POST'], detail=False, url_path='bulk-payment')
    def bulk_payment(self, request):
        try:
            diagnosis_id = request.data.get('diagnosisID')
            
            if not diagnosis_id:
                return Response(
                    data={'errMsg': 'diagnosisID is required'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            from mainApp.models import Diagnosis, Prescribing, PrescriptionDetail
            
            try:
                diagnosis = Diagnosis.objects.get(id=diagnosis_id)
                prescribing_list = Prescribing.objects.filter(diagnosis=diagnosis, active=True)
                
                if not prescribing_list.exists():
                    return Response(
                        data={'errMsg': 'No prescribing found for this diagnosis'}, 
                        status=status.HTTP_404_NOT_FOUND
                    )
                
                prescribing_amounts = {}
                total_medicine_cost = 0
                
                for prescribing in prescribing_list:
                    prescription_details = PrescriptionDetail.objects.filter(
                        prescribing=prescribing, 
                        active=True
                    )
                    
                    prescribing_total = 0
                    for detail in prescription_details:
                        medicine_cost = detail.medicine_unit.price * detail.quantity
                        prescribing_total += medicine_cost
                    
                    prescribing_amounts[prescribing.id] = prescribing_total
                    total_medicine_cost += prescribing_total
                
                service_fee = SERVICE_FEE_PER_PRESCRIBING  # Phí dịch vụ 1 lần cho 1 lần khám
                
                created_bills = []
                for prescribing in prescribing_list:
                    if not Bill.objects.filter(prescribing=prescribing).exists():
                        # Chia đều phí khám cho các prescribing, tiền thuốc giữ nguyên
                        service_fee_per_prescribing = service_fee / len(prescribing_list)
                        medicine_cost = prescribing_amounts.get(prescribing.id, 0)
                        total_amount = medicine_cost + service_fee_per_prescribing
                        
                        bill = Bill.objects.create(
                            prescribing=prescribing, 
                            amount=total_amount
                        )
                        created_bills.append({
                            'prescribing_id': prescribing.id,
                            'medicine_cost': medicine_cost,
                            'service_fee': service_fee_per_prescribing,
                            'total_amount': total_amount
                        })
                
                return Response({
                    'message': f'Successfully created {len(created_bills)} bills',
                    'total_medicine_cost': total_medicine_cost,
                    'total_service_fee': service_fee,
                    'total_amount': total_medicine_cost + service_fee,
                    'created_bills': created_bills,
                    'created_bills_count': len(created_bills)
                }, status=status.HTTP_201_CREATED)
                
            except Diagnosis.DoesNotExist:
                return Response(
                    data={'errMsg': 'Diagnosis not found'}, 
                    status=status.HTTP_404_NOT_FOUND
                )
                
        except Exception as e:
            print(f"Error in bulk_payment: {str(e)}")
            return Response(
                data={'errMsg': 'Internal server error'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(methods=['POST'], detail=False, url_path='zalo-payments')
    def zalo_payments(self, request):
        config = {
            "app_id": 2553,
            "key1": "PcY4iZIKFCIdgZvA6ueMcMHHUbRLYjPL",
            "key2": "kLtgPl8HHhfvMuDHPwKfgfsY4Ydm9eIz",
            "endpoint": "https://sb-openapi.zalopay.vn/v2/create",
            "callback_url": 'http://localhost:5173/',
        }
        transID = random.randrange(1000000)
        order = {
            "app_id": config["app_id"],
            "app_trans_id": "{:%y%m%d}_{}".format(datetime.today(), transID),  # mã giao dich có định dạng yyMMdd_xxxx
            "app_user": "user123",
            "app_time": int(round(time() * 1000)),  # miliseconds
            "embed_data": json.dumps({}),
            "item": json.dumps([{}]),
            "amount": request.data.get('amount'),
            "callback_url": config["callback_url"],
            "description": "Lazada - Payment for the order #" + str(transID),
            "bank_code": "zalopayapp"

        }

        # app_id|app_trans_id|app_user|amount|apptime|embed_data|item
        data = "{}|{}|{}|{}|{}|{}|{}".format(order["app_id"], order["app_trans_id"], order["app_user"],
                                             order["amount"], order["app_time"], order["embed_data"], order["item"])
        print("-------------------- Data ----------------\n")
        print(data)
        order["mac"] = hmac.new(config['key1'].encode(), data.encode(), hashlib.sha256).hexdigest()
        print(order["mac"])
        response = urllib.request.urlopen(url=config["endpoint"], data=urllib.parse.urlencode(order).encode())
        result = json.loads(response.read())

        print("-------------------- Result  ----------------\n")
        print(result)
        for k, v in result.items():
            print("{}: {}".format(k, v))

        return Response(data={"order_url": result['order_url'], 'order_token': result['order_token']},
                        status=status.HTTP_200_OK)

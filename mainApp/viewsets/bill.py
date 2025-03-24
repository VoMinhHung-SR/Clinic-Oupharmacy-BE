import hashlib
import hmac
import json
import os
import urllib
import uuid
from datetime import datetime, time
from random import random

from django.http.response import HttpResponseRedirect
from rest_framework.decorators import action
from rest_framework import viewsets, generics

from mainApp.models import Bill, Prescribing
from mainApp.serializers import BillSerializer
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework import status

class BillViewSet(viewsets.ViewSet, generics.CreateAPIView,
                  generics.DestroyAPIView, generics.RetrieveAPIView,
                  generics.UpdateAPIView, generics.ListAPIView):
    queryset = Bill.objects.filter(active=True)
    serializer_class = BillSerializer
    parser_classes = [JSONParser, MultiPartParser]

    def get_parsers(self):
        if getattr(self, 'swagger_fake_view', False):
            return []

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
            prescribing_id = Prescribing.objects.get(id=int(request.GET['prescribingId']))

            examination_id = prescribing_id.diagnosis.examination.id
            if request.GET['resultCode'] != str(0):
                return HttpResponseRedirect(redirect_to=os.getenv('CLIENT_SERVER')+'/examinations/' + str(examination_id) + '/payments')
            else:
                Bill.objects.create(prescribing=prescribing_id, amount=float(request.GET['amount']))
        except:
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            data={'errMgs': 'prescriptionId or examinationId not found'})

        return HttpResponseRedirect(redirect_to=os.getenv('CLIENT_SERVER')+'/examinations/' + str(examination_id) + '/payments')

    @action(methods=['POST'], detail=False, url_path='momo-payments')
    def momo_payments(self, request):
        prescribing = str(request.data.get('prescribing'))

        endpoint = "https://test-payment.momo.vn/v2/gateway/api/create"
        partnerCode = "MOMOPZQO20220908"
        accessKey = "YCyiVT9bM5fS3W72"
        secretKey = "v2srvmKzz6f5wVht5OwcXWErUhBdn4tq"
        orderInfo = "Pay with MoMo"
        # Redirect Server URL
        redirectUrl = os.getenv('SERVER') + "/bills/bill_status?prescribingId="+prescribing
        # Redirect Client URL
        ipnUrl = os.getenv('SERVER') + "/bills/bill_status/"
        amount = str(request.data.get('amount'))
        orderId = str(uuid.uuid4())
        requestId = str(uuid.uuid4())
        requestType = "captureWallet"
        extraData = ""  # pass empty value or Encode base64 JsonString

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
            'prescribingId': prescribing,
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
        response = request.post(endpoint, data=data,
                                 headers={'Content-Type': 'application/json', 'Content-Length': str(clen)})

        # f.close()
        print("--------------------JSON response----------------\n")
        print(response.json())

        user = request.user
        if user:
            return Response(data={"payUrl": response.json()['payUrl']}, status=status.HTTP_200_OK)

        return Response(data={'errMgs': "User not found"},
                        status=status.HTTP_400_BAD_REQUEST)

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

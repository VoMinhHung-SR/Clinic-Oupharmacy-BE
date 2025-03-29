from .bill import BillSerializer
from .category import CategorySerializer
from .common_location import CommonDistrictSerializer, CommonLocationSerializer, CommonCitySerializer
from .diagnosis import DiagnosisSerializer, DiagnosisCRUDSerializer, DiagnosisStatusSerializer
from .doctor_schedule import DoctorScheduleSerializer
from .examination import ExaminationSerializer
from .medicine import MedicineSerializer
from .medicine_unit import MedicineUnitSerializer
from .patient import PatientSerializer
from .prescribing import PrescribingSerializer
from .prescribing_detail import PrescriptionDetailSerializer, PrescriptionDetailCRUDSerializer
from .user import UserSerializer
from .user_role import UserRoleSerializer, UserNormalSerializer
from .time_slot import TimeSlotSerializer
from dotenv import load_dotenv
load_dotenv()

from services.maps_service import get_distance_and_time

print(get_distance_and_time("Vartak Nagar, Thane", "Cadbury Junction, Thane"))
print(get_distance_and_time("51.4822656,-0.1933769", "51.4994794,-0.1269979"))  # example London coords test

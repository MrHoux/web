import logging

logger = logging.getLogger(__name__)


def validate_address(address_data):
    # Mock implementation: simple validation
    valid = bool(
        address_data.get('province') and
        address_data.get('city') and
        address_data.get('district') and
        address_data.get('detail_address')
    )

    return {
        'valid': valid,
        'suggestions': [],
        'lat': None,
        'lng': None,
        'baidu_place_id': None
    }


def geocode_address(address_text):
    # Mock implementation: return None
    logger.info(f"Geocoding (Mock): {address_text}")
    return {
        'lat': None,
        'lng': None,
        'baidu_place_id': None
    }


def reverse_geocode(lat, lng):
    # Mock implementation
    logger.info(f"Reverse geocoding (Mock): lat={lat}, lng={lng}")
    return {
        'address': None,
        'province': None,
        'city': None,
        'district': None
    }

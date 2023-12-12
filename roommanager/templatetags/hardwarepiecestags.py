from django import template
from roommanager.models import Machine, CardReaderAsset, Slot
register = template.Library()


def _get_adminurl_and_piece(asset_code, asset_type):
    if asset_type == 'CARD_READER':
        admin_url = 'http://system.aceslaundry.com/admin/roommanager/cardreaderasset/{}/change/'
        piece = CardReaderAsset.objects.filter(card_reader_tag=asset_code).first()
    elif asset_type == 'MACHINE':
        admin_url = 'http://system.aceslaundry.com/admin/roommanager/machine/{}/change/'
        piece = Machine.objects.filter(asset_code=asset_code).first()
    elif asset_type == 'SLOT':
        admin_url = 'http://system.aceslaundry.com/admin/roommanager/slotview/{}/change/'
        if isinstance(asset_code, int): piece = Slot.objects.get(id=asset_code)
        else: piece = asset_code
    else:
        piece = None
    return admin_url, piece

@register.simple_tag
def get_asset_urls(asset_code, asset_type):
    fascard_url = None
    admin_url, piece = _get_adminurl_and_piece(asset_code, asset_type)
    urls = []
    if not piece: return urls
    if asset_type == 'SLOT': fascard_url = 'https://admin.fascard.com/86/machine?locid={}&machid={}'
    urls.append((admin_url.format(piece.id), 'Admin Dashboard URL'))
    if hasattr(piece, 'upkeep_id') and getattr(piece, 'upkeep_id'):
        upkeep_url = 'https://app.onupkeep.com/#/app/assets/view/{}'
        urls.append((upkeep_url.format(piece.upkeep_id), 'Upkeep URL'))
    if hasattr(piece, 'maintainx_id') and getattr(piece, 'maintainx_id'):
        maintainx_url = 'https://app.getmaintainx.com/assets/{}'
        urls.append((maintainx_url.format(piece.maintainx_id), 'Maintainx URL'))
    if fascard_url:
        #piece must be slot
        fascard_url_formatted = fascard_url.format(
            piece.laundry_room.fascard_code,
            piece.slot_fascard_id)
        urls.append((fascard_url_formatted, 'Fascard URL'))
    return urls

@register.simple_tag
def get_admin_url(asset_code, asset_type):
    admin_url, piece = _get_adminurl_and_piece(asset_code, asset_type)
    if piece: return admin_url.format(piece.id)
    else: return None

@register.simple_tag
def get_machine_pics(asset_code: str) -> list:
    images = []
    try:
        machine = Machine.objects.get(asset_code=asset_code)
        if machine.asset_picture: images.append(('Asset Picture', machine.asset_picture))
        if machine.asset_serial_picture: images.append(('Asset Serial Picture', machine.asset_serial_picture))
    except Machine.DoesNotExist:
        pass
    return images

@register.simple_tag(takes_context=True)
def get_domain(context) -> str:
    URL = ""
    request = context['request']
    HTTP_HOST = request.META['HTTP_HOST']
    # HTTP or HTTPS
    secure_request = request.is_secure()

    if secure_request: URL = f"https://{HTTP_HOST}"
    else: URL = f"http://{HTTP_HOST}"

    return URL
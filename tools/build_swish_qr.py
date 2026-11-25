"""Build-time only: pip install 'qrcode[pil]'. No QR service or runtime dependency.

Swish C-format: fixed recipient, empty amount, message FolderForge.
Mask 6 allows amount/message edits in Swish, not recipient edits.
A QR is public payment data, not encryption or proof of recipient identity.
"""
from pathlib import Path

SWISH_PAYLOAD = 'C46721817177;;FolderForge;6'


def build():
    import qrcode
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=12, border=4)
    qr.add_data(SWISH_PAYLOAD)
    qr.make(fit=True)
    target = Path(__file__).resolve().parents[1] / 'Icon/swish-folderforge.png'
    qr.make_image(fill_color='black', back_color='white').save(target)
    return target


if __name__ == '__main__':
    print(build())

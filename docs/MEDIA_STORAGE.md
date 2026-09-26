# Media Storage — Argentina Dispensary CDMS

Uploads handled by this setting:

| What | Field |
|---|---|
| Patient QR codes | `patients.Patient.qr_code` |
| Patient documents | `patients.PatientDocument.document` |
| Ultrasound images | `ultrasound.UltrasoundReport.image` |

Static assets (CSS, JS, images bundled with the app) are **not** affected —
those still go through WhiteNoise and `collectstatic`.

---

## How the backend is chosen

`hms_project/settings.py` reads `AWS_STORAGE_BUCKET_NAME` from the
environment:

- **Not set → local disk.** `FileSystemStorage` writing to `media/`. This is
  development and single-machine behaviour, unchanged from before.
- **Set → object storage.** `storages.backends.s3.S3Storage`, served directly
  from the bucket or CDN. No Django URL is registered for `/media/`.

Nothing is hard-coded. There is no bucket name, endpoint, region, access key
or secret anywhere in the source tree.

---

## Environment variable names

Set these in the host's secret store. **Values are never committed.**

Required for object storage:

```
AWS_STORAGE_BUCKET_NAME
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
AWS_S3_REGION_NAME
```

Optional:

```
AWS_S3_ENDPOINT_URL            non-AWS providers (MinIO, DigitalOcean Spaces, Cloudflare R2, Backblaze B2)
AWS_S3_CUSTOM_DOMAIN           CDN or public bucket domain, serves files faster
AWS_QUERYSTRING_AUTH           default true; set false for a fully public bucket
AWS_S3_OBJECT_CACHE_CONTROL    default max-age=86400
AWS_S3_SIGNATURE_VERSION       default s3v4
```

Leave `AWS_STORAGE_BUCKET_NAME` unset locally and everything keeps working
from the `media/` folder.

---

## Serving uploads in production

`urls.py` no longer relies on `DEBUG` for `/media/`:

| Backend | `DEBUG=False` behaviour |
|---|---|
| Object storage | No `/media/` route; `file.url` returns the bucket/CDN URL |
| Local disk | `/media/<path>` served by Django as a fallback |

The local-disk fallback exists so a VPS works before nginx is configured. Once
nginx handles `/media/`, serve the volume from there and the Django route
becomes redundant.

Temporary hosting platforms have an **ephemeral filesystem** — anything in
`media/` is lost on every redeploy. On temporary hosting, object storage is
required, not optional.

---

## Verifying the setup

```bash
# should print True
python -c "import django,os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','hms_project.settings'); django.setup(); from django.conf import settings; print(settings.USING_S3_STORAGE)"

# should print the S3 backend class
python -c "import django,os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','hms_project.settings'); django.setup(); from django.conf import settings; print(settings.STORAGES['default']['BACKEND'])"
```

Upload a QR code and a patient document through the UI, then confirm they
appear in the bucket under `patient_qr/` and `patient_docs/`.

The IAM user or role needs `s3:PutObject`, `s3:GetObject`, `s3:DeleteObject`
and `s3:ListBucket` on that bucket only. Block public access on the bucket and
leave `AWS_QUERYSTRING_AUTH` enabled so files stay private.

No real bucket has been created or connected while preparing this.

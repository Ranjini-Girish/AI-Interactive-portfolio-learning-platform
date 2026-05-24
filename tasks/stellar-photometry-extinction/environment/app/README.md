# Stellar Photometry Extinction Audit

Reduces multi-night CCD photometry from the Cerro Andino Observatory archive
into per-night extinction fits, calibrated lightcurves for the program-star
list, and a quality-control finding ledger.

```
make -C /app build
/app/bin/photo_audit --data /app/data --out /app/output/photometry_report.json
```

The starter `src/photo_audit.cpp` writes a stub report. Replace its body with
your implementation, or rewrite the binary in another language; the harness
only checks the contents of `/app/output/photometry_report.json` and that the
binary at `/app/bin/photo_audit` is runnable. The full algorithm lives under
`/app/docs/`.

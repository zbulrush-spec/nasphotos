# MT Photos InsightFace integration

Source: https://github.com/dev-fox-101/mt-photos-insightface-unofficial
Revision: a67c00208fc2f8138ad61223079675b59f4372dd

`upstream_server.py` is an unchanged copy of that revision's `server.py`.
`UPSTREAM_README.md` preserves its setup and API documentation.
`server.py` adapts model location, loopback binding, CPU limits and idle unloading.
The original API remains inside the same NAS Photos container on 127.0.0.1:8066.
Only the authenticated photo application can submit recognition work from outside.

InsightFace library: https://github.com/deepinsight/insightface (MIT).
The buffalo_l pretrained models have separate upstream terms: non-commercial
research only. See https://github.com/deepinsight/insightface/tree/master/python-package
and https://github.com/deepinsight/insightface/tree/master/model_zoo .
Model packaging does not grant additional commercial rights.

Leaflet 1.9.4 is bundled under `static/vendor/leaflet` with its BSD-2-Clause
license. OpenStreetMap tiles retain visible attribution on the map.

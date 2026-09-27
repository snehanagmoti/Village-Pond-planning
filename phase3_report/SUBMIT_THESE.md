# Phase 3: final submission items

1. **Final report:** `output/pdf/Phase_3_Final_Technical_Report.pdf`.
2. **GitHub:** https://github.com/snehanagmoti/Village-Pond-planning
3. **Working frontend:** http://10.1.75.53:3238/
4. **Public YouTube demo:** finish the voice-over and final edit of the existing demo, keep it at most five minutes, upload publicly, and paste the resulting URL. No video has been uploaded on your behalf.

Extra reference for the evaluator:

- Swagger: http://10.1.75.53:3238/docs
- API: `POST http://10.1.75.53:3238/api/analyze-contour`
- Multipart file key: `contour_map`
- Allotted host: system 2, SSH port 2238. Browser port 3238 maps to internal port 3000; do not submit the SSH port as a website.

The college URLs require college-network/VPN connectivity. Open them on the network the evaluator will use. Confirm the sample KML and a live analysis before recording. Source outages are not a valid complete result; allow the explicit retry rather than hiding the status.

## If the container has rebooted

SSH into system 2, then run:

```sh
sh "$HOME/pond-phase3-release/start_lab_service.sh"
```

The service survives SSH logout and automatically recovers an application-process exit. Container reboot startup is manual; this avoids claiming a boot service exists where the host runs SSH as its initial process.

## Final user actions

- Review the report and rehearse the algorithm explanation.
- Finish the voice-over/edit and publicly upload the demo, verify the link signed out, and add it with the other three items.
- Upload the final report and submit the Classroom assignment yourself. No Classroom submission or YouTube publication has been performed automatically.

"""PySide6 desktop apps built on the shared GpuMeasurementService.

Two products share one measurement core (per the development brief):

- ``buyer``    : GPU Check  — single-device inspection for used-GPU buyers
- ``operator`` : GPU Ops    — repeated checks and history for AI server operators

The frontend never calls the collector or nvidia-smi directly and never
reimplements TFLOPS or diagnostics; all measurement runs through the service and
a background worker so the UI stays responsive and cancellable.
"""

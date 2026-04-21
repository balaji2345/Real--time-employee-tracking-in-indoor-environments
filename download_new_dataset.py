from roboflow import Roboflow

rf = Roboflow(api_key="GtdXHnYe9yKK9vyt8ASJ")
project = rf.workspace("indian-dataset-e3sb5").project("workforce-monitor")
version = project.version(3)
dataset = version.download("yolov8")

print("Downloaded to:", dataset.location)
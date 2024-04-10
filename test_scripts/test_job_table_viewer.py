import sys
from pandas import read_csv
from PyQt5.QtWidgets import QApplication

from gui import JobTableViewer

df = read_csv("../example_data/python_jobs_10042024.csv", )

app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(True)

table_viewer = JobTableViewer()
table_viewer.setFixedSize(1280, 720)
table_viewer.display_jobs(df)
table_viewer.show()

app.exec_()

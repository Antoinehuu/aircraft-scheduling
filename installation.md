---
title: Installation Tutorial
---

## Clone the project

```bash
git clone https://github.com/antoinehuu/aircraft-scheduling.git
cd aircraft-scheduling
```

---

## Create a virtual environment

Gurobi only support 3.10, 3.11, 3.12, 3.13, 3.14 python version, if you have a > 3.14 version replace python3 by python3.14
### On Linux/Mac:
```bash
python3 -m venv venv
source venv/bin/activate
```

### On Windows:
```bash
python -m venv venv
venv\Scripts\activate
```

---

### Gurobi

Requires a Gurobi license; there is a tutorial for an academic license at the end.

```bash
pip install -r requirements.txt
```

### Hexaly

Install the optional Python package with 

```bash
python -m pip install hexaly
```

and configure a Hexaly license. See the [Hexaly setup guide](https://www.hexaly.com/docs/last/installation/pythonsetup.html).

---

## Gurobi Academic license installation

• Go to the main page of the Gurobi website and log in to your Gurobi account via the Login tab, if
you are not already logged in.

• Click on the Downloads and licenses tab. In the Request a license paragraph, click on the
Academic License tab.

• Accept the terms of use of the academic license. As you can see, your Gurobi academic license has been generated. You can now install your license by following the
instructions given in the Installation paragraph under the details table. We give a few
additional indications below:

– On macOS or Linux.

* Copy the command grbgetkey <key>, open a terminal window, paste the command into
your terminal window and run it. You are asked to choose the folder in which to store
your license file; press Enter to choose the default folder. We recommend
choosing the default folder and not a personal folder, otherwise this generates additional steps
(setting an environment variable via command line, etc.).

* You can check that your license is properly installed by typing the command gurobi.sh and
checking that a line Academic license - for non-commercial use only - expires <date> is written
in the displayed text.

– On Windows.

* Open the Gurobi shell by double-clicking on the Gurobi9.1.1 icon added to the desktop after
installation.

* Enter the <key> provided in the Installation paragraph.

* Specify the name of the directory where to store the license file or press the Enter key on the
keyboard to select the default location.
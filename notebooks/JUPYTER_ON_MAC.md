# Running the notebooks on a Mac

The notebooks use the isolated environment in `notebooks/.venv`. It contains the frozen WISE package and a kernel named **WISE paper (frozen)**. The package imports as `wise`, so keep it separate from the development library that uses the same import name.

## First setup

Open Terminal in the `wise-pm-library` project folder. Python 3.11 or newer must be available as `python3`. Run:

```sh
cd notebooks
bash setup_environment.sh
```

Setup creates or updates `.venv`, installs the package with its notebook dependencies and registers the kernel inside that environment. The final message confirms that package version 1.0.1 and the functions for its 38 result items are available. The existing environment is ready to use; setup is unnecessary for an ordinary session.

## Start a session

From the `notebooks` folder, run:

```sh
bash start_jupyter.sh "DATA_FOLDER"
```

Replace `DATA_FOLDER` with the folder containing the datasets. Quotes allow spaces in the folder name. Use the folder itself, rather than the name of an individual file. The launcher calls Jupyter from `.venv` directly, so you do not need to activate the environment.

Alternatively, set the single data-folder variable in that Terminal session:

```sh
export WISE_PAPER_DATA="DATA_FOLDER"
bash start_jupyter.sh
```

The browser should open JupyterLab with `WISE_Section_V_Evaluation.ipynb`. The complete result catalogue is in `WISE_Evaluation.ipynb`, available from the file browser. If JupyterLab does not open automatically, copy the complete local browser URL printed in Terminal, including its access token, into your browser. Keep that Terminal window open while working.

In JupyterLab, select **WISE paper (frozen)** from the kernel menu. Open a dataset notebook from the file browser on the left:

- `BPIC2019_PurchaseToPay_Extended.ipynb` for purchasing and payment.
- `BPIC2013_Incidents_Extended.ipynb` for incident management.
- `BPIC2017_Lending_Extended.ipynb` for loan applications.

Run the cells in order, or choose **Run → Run All Cells**. The first cells check the package and dataset. A missing-input message means the data folder or required dataset needs checking. Tables and figures are written to the ignored `outputs` folder.

## Finish or update

Save your work, then return to Terminal and press **Control-C**. Confirm shutdown if prompted. Closing a browser tab alone does not stop the server.

If you manually activated the environment with `source .venv/bin/activate`, run `deactivate` after shutdown. Activation is optional when using the launcher.

After a package update, stop Jupyter, rerun `bash setup_environment.sh`, then start a new session with the same launch command. Restart the notebook kernel before running cells so it imports the updated installation. Setup does not require installing the development library into this environment.

See the [notebook guide](README.md) for the available analyses.

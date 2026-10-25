from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session
from flask_session import Session
from functools import wraps
import json, os, uuid
import numpy as np
import pandas as pd
import psycopg
from psycopg.rows import dict_row
from scipy.integrate import solve_ivp
from scipy.optimize import minimize
from werkzeug.security import check_password_hash, generate_password_hash

# Configure application
app = Flask(__name__)

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

load_dotenv()  # reads .env if it exists; does nothing on Render

app.secret_key = os.environ["SECRET_KEY"]
DATABASE_URL = os.environ["DATABASE_URL"]

# connect to database
def db():
    """ Connect to postgres db """
    return psycopg.connect(DATABASE_URL)

# FUNCTIONS
def error_func(x, t, t_span, XSP_init, X_exp, S_exp, P_exp):
    umax, Ks, Ysx, Ypx = x
    ivp_solution = ivp(umax, Ks, Ysx, Ypx, XSP_init, t, t_span)
    X_solve, S_solve, P_solve = ivp_solution.y
    error = sum((X_solve - X_exp) ** 2 + (S_solve - S_exp) ** 2 + (P_solve - P_exp) ** 2)
    return error


def ivp(umax, Ks, Ysx, Ypx, XSP_init, t, t_span):
    umax, Ks, Ysx, Ypx = (umax, Ks, Ysx, Ypx)

    def monod(t, Y, umax=umax, Ks=Ks, Ysx=Ysx, Ypx=Ypx):
        X,S,P = Y
        u = umax * S / (Ks + S)
        dXdt = u * X
        dSdt = -1 / Ysx * dXdt
        dPdt = Ypx * dXdt
        return dXdt, dSdt, dPdt
    
    solution = solve_ivp(monod, t_span, XSP_init, t_eval=t)
    return solution


def r_squared(observed, predicted):
    ss_res = np.sum((observed - predicted) ** 2)
    ss_tot = np.sum((observed - np.mean(observed)) ** 2)
    return np.nan if ss_tot == 0 else round(1 - ss_res / ss_tot, 3)


# DECORATOR FUNCTIONS
def login_required(f):
    """ Decorate routes to require login. """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return f(*args, **kwargs)

    return decorated_function

@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# ROUTES
@app.route("/")
@login_required
def index():
    """ Main app page """

    # clear temporary memory of df, coeff, and plotter
    session["df"] = None
    session["coeff"] = None
    session["plotter"] = None

    return render_template("index.html")


@app.route("/fit", methods=["POST"])
@login_required
def fit():
    # unpack the dataframe from the payload and validate
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("dataframe"), list):
        return jsonify(success=False, err_message="no dataframe provided")

    try:
        df = pd.DataFrame(payload["dataframe"])
    except Exception as e:
        return jsonify(success=False, err_message=f"invalid dataframe: {e}")

    # rename column name to convention
    col_map = {
        "time": "t",
        "biomass": "X",
        "substrate": "S",
        "product": "P",
        "t": "t",
        "x": "X",
        "s": "S",
        "p": "P",
    }
    df = df.rename(columns={col: col_map[col.lower()] for col in df.columns})

    # fitting
    # initial guess
    umax_init = 0.5
    Ks_init = 0.5
    Yxs_init = 0.5
    Ypx_init = 0.5
    # adjust data structure
    t = df['t'].to_numpy()
    t = np.astype(t, float)
    t_span = (t[0], t[-1])
    X_exp = df['X'].to_numpy()
    S_exp = df['S'].to_numpy()
    P_exp = df['P'].to_numpy()
    # initialisation
    XSP_init = (X_exp[0], S_exp[0], P_exp[0])
    coeff_init = (umax_init, Ks_init, Yxs_init, Ypx_init)
    # fitting
    opt_coeff = minimize(error_func, coeff_init, args=(t, t_span, XSP_init, X_exp, S_exp, P_exp))    
    opt_coeff_round = [round(x, 3) for x in opt_coeff.x]
    umax_opt, Ks_opt, Ysx_opt, Ypx_opt = opt_coeff_round
    # generate plot for viusalisation
    # t_ivp = np.arange(t_span[0], t_span[1], (t_span[1] - t_span[0]) / 100)
    ivp_solution = ivp(umax_opt, Ks_opt, Ysx_opt, Ypx_opt, XSP_init, t, t_span)
    # calculate R squared
    r2 = {
        "X": r_squared(X_exp, ivp_solution.y[0]),
        "S": r_squared(S_exp, ivp_solution.y[1]),
        "P": r_squared(P_exp, ivp_solution.y[2]),
    }

    # package the result to be sent to the client
    plotter = [
        {
            "name": "Biomass (fit)",
            "x" : ivp_solution.t.tolist(),
            "y" : ivp_solution.y[0].tolist(),
            "type" : "scatter",
            "mode" : "line",
            "line" : {
                "color" : "#eead20",
                "shape" : "spline",
                "smoothing" : 0.5
            }
        },
        {
            "name": "Substrate (fit)",
            "x" : ivp_solution.t.tolist(),
            "y" : ivp_solution.y[1].tolist(),
            "type" : "scatter",            
            "mode" : "lines",
            "line" : {
                "color" : "#de5a5a",
                "shape" : "spline",
                "smoothing" : 0.5
            }
        },
        {
            "name": "Product (fit)",
            "x" : ivp_solution.t.tolist(),
            "y" : ivp_solution.y[2].tolist(),
            "type" : "scatter",            
            "mode" : "lines",
            "line" : {
                "color" : "#5e5cd0",
                "shape" : "spline",
                "smoothing" : 0.5
            }      
        },
        {
            "name": "Biomass (data)",
            "x" : t.tolist(),
            "y" : X_exp.tolist(),
            "mode" : "markers",
            "marker" : {
                "color" : "#eead20",
                "symbol" : "triangle-up"
            }            
        },
        {
            "name": "Substrate (data)",
            "x" : t.tolist(),
            "y" : S_exp.tolist(),
            "mode" : "markers",
            "marker" : {
                "color" : "#de5a5a",
                "symbol" : "triangle-up"
            }                            
        },
        {
            "name": "Product (data)",
            "x" : t.tolist(),
            "y" : P_exp.tolist(),
            "mode" : "markers",
            "marker" : {
                "color" : "#5e5cd0",
                "symbol" : "triangle-up"
            }                            
        }
    ]

    coeff = {
        "umax" : umax_opt,
        "Ks" : Ks_opt,
        "Ysx" : Ysx_opt,
        "Ypx" : Ypx_opt,
        "r2" : r2
    }

    # store in session
    session["plotter"] = plotter
    session["coeff"] = coeff 
    session["df"] = df

    return jsonify(
        success=True,
        err_message="dataframe received",
        plotter=plotter,
        coeff=coeff
    )


@app.route("/health")
def health():
    return "ok", 200


@app.route("/login", methods=["GET", "POST"])
def login():
    """ Log user in """

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return jsonify(success=False, err_message="provide a username")

        # Ensure password was submitted
        elif not request.form.get("password"):
            return jsonify(success=False, err_message="provide a password")

        # Query database for username
        with db() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM users WHERE username = %s",
                (request.form.get("username"),)
            )

            rows = cur.fetchall()

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0][2], request.form.get("password")
        ):
            return jsonify(success=False, err_message="invalid username and/or password")

        # Remember which user has logged in
        session["user_id"] = rows[0][0]

        # return exit status
        return jsonify(success=True)

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/open", methods=["POST"])
@login_required
def open_project():
    """ Serves a list of projects and open the selected """

    data = request.get_json()

    if data["request"] == "fetchProjects":
        with db() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT name FROM data WHERE user_id = %s",
                (session["user_id"],)
            )
            projects = cur.fetchall()

        return jsonify(projects)      
    
    elif data["request"] == "loadProject":
        with db() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT project FROM data WHERE user_id = %s AND name = %s",
                (session["user_id"], data["projectName"])
            )
            project = cur.fetchone()

        return jsonify(project[0])        


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    if request.method == "POST":
        # retrieve values via post method
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # if username or password are empty, render an apology
        is_username_empty = not username or not username.strip()
        is_password_empty = not password

        if is_username_empty or is_password_empty:
            err_message = "provide "
            if is_username_empty and not is_password_empty:
                err_message += "a username"
            elif not is_username_empty and is_password_empty:
                err_message += "a password"
            elif is_username_empty and is_password_empty:
                err_message += "username and password"

            return jsonify(success=False, err_message=err_message)

        # if password confirmation does not match, render an apology
        if password != confirmation:
            return jsonify(success=False, err_message="password confirmation mismatch")

        # once passed the checkpoint, try to insert a new username (must be unique)
        password_hash = generate_password_hash(password)

        # generate user id
        user_id = str(uuid.uuid4())

        try:
            with db() as conn, conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO users (id, username, hash) VALUES(%s, %s, %s)",
                    (user_id, username, password_hash)
                )
                conn.commit()
        except psycopg.errors.UniqueViolation:
            return jsonify(success=False, err_message="username already exists")

        # add a defult example project
        with open('static/json/example.json', mode='r', encoding='utf-8') as file:
            example_project = file.read()

        with db() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO data (user_id, name, project) "
                "VALUES (%s, %s, %s) "
                "ON CONFLICT (user_id, name) "
                "DO UPDATE SET project = EXCLUDED.project",
                (user_id, "example", example_project),
            )
            conn.commit()

        return jsonify(success=True)

    else:
        return render_template("register.html")


@app.route("/save", methods=["POST"])
@login_required
def save_project():
    """ Save a project in JSON format and send to database """

    # retrieve project name
    project_name = request.data.decode('utf-8')

    # pack the project
    plotter = session.get("plotter", None)
    coeff = session.get("coeff", None)
    df = session.get("df", None)

    project = {
        "name" : project_name,
        "plotter" : plotter,
        "coeff" : coeff,
    }

    if not df.empty:
        project["df"] = df.to_dict(orient="records")
    else:
        project["df"] = None

    with db() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO data (user_id, name, project) "
            "VALUES (%s, %s, %s) "
            "ON CONFLICT (user_id, name) "
            "DO UPDATE SET project = EXCLUDED.project",
            (session["user_id"], project_name, json.dumps(project)),
        )
        conn.commit()

    return jsonify(success=True, message="Project saved")


@app.route("/upload", methods=["POST"])
@login_required
def upload():
    """ Do fitting towards data in a newly uploaded csv """

    # retrieve the new csv file
    new_file = request.files.get("newFile")

    # check if empty
    if not new_file:
        return jsonify(success=False, err_message="no file found")

    # validate format
    try:
        df = pd.read_csv(new_file.stream, encoding="utf-8")
    except Exception as e:
        return jsonify(success=False, err_message=f"failed to read file: {e}")
    
    # validate header
    valid_col_static = set(("time", "biomass", "substrate", "product", "t", "x", "s", "p"))
    valid_col_dynamic = valid_col_static.copy()
    for i in range(len(df.columns)):
        col = df.columns[i]
        if not col.lower() in valid_col_static:
            return jsonify(success=False, err_message=f"invalid column name: {col}")
        elif col.lower() in valid_col_static and not col.lower() in valid_col_dynamic:
            return jsonify(success=False, err_message=f"extraneous column (index, name): {i}, {col}")
        else:
            valid_col_dynamic.remove(col.lower())

    # validate values
    df = df.apply(pd.to_numeric, errors='coerce')
    row_idx, col_idx = np.where(df.isna())
    nan_coordinates = list(zip(row_idx.tolist(), col_idx.tolist()))

    if len(nan_coordinates) > 0:
        return jsonify(success=False, err_message=f"invalid value: {str(nan_coordinates)}")

    # check if dataset too long
    if len(df) > 100:
        return jsonify(success=False, err_message="dataset too large (max 100 rows)")

    return jsonify(success=True, dataframe=df.to_dict(orient="records"))
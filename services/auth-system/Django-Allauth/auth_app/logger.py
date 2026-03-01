import logging
from django.conf import settings
from pathlib import Path
import functools
import inspect

# ----------------- Logger Setup -----------------
LOG_DIR = getattr(settings, "LOG_DIR", Path(__file__).resolve().parent / "logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "auth.log"

logger = logging.getLogger("auth_app")
logger.setLevel(logging.INFO)

if not logger.handlers:
    console_handler = logging.StreamHandler()
    console_formatter = logging.Formatter("[%(asctime)s] %(levelname)s %(name)s %(message)s")
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    file_handler = logging.FileHandler(LOG_FILE)
    file_formatter = logging.Formatter("[%(asctime)s] %(levelname)s %(name)s %(message)s")
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

# ----------------- Convenience -----------------
def info(msg, *args, **kwargs):
    logger.info(msg, *args, **kwargs)

def debug(msg, *args, **kwargs):
    logger.debug(msg, *args, **kwargs)

def warning(msg, *args, **kwargs):
    logger.warning(msg, *args, **kwargs)

def error(msg, *args, **kwargs):
    logger.error(msg, *args, **kwargs)

def exception(msg, *args, **kwargs):
    logger.exception(msg, *args, **kwargs)

# ----------------- Helpers -----------------
def sanitize_arg(arg):
    """Skip long HTML or binary content in logs."""
    if isinstance(arg, str):
        if "<html" in arg.lower() or len(arg) > 200:
            return f"<{type(arg).__name__} content skipped>"
    return arg

# ----------------- Auto-wrap views -----------------
def log_view(func):
    """Decorator to log function call, args, return, and exceptions cleanly."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            safe_args = tuple(sanitize_arg(a) for a in args)
            safe_kwargs = {k: sanitize_arg(v) for k, v in kwargs.items()}
            info(f"CALL {func.__name__} args={safe_args} kwargs={safe_kwargs}")

            result = func(*args, **kwargs)

            # Log only type/status for responses
            if hasattr(result, "status_code"):
                info(f"RETURN {func.__name__} => <{type(result).__name__} status_code={result.status_code}>")
            else:
                info(f"RETURN {func.__name__} => {sanitize_arg(result)}")
            return result

        except Exception as e:
            exception(f"EXCEPTION in {func.__name__}: {e}")
            raise
    return wrapper

def wrap_all_views(module):
    """Wrap all functions in a module with the logging decorator."""
    for name, obj in inspect.getmembers(module):
        if inspect.isfunction(obj):
            setattr(module, name, log_view(obj))
    info(f"✅ All view functions in {module.__name__} wrapped with logging.")

# ----------------- Master block -----------------
try:
    import auth_app.views as views
    wrap_all_views(views)
    info("✅ auth_app.views imported successfully and auto-logged.")
except Exception as e:
    exception(f"❌ Failed to wrap auth_app.views: {e}")

@echo off
echo Collecting static files...
python manage.py collectstatic --noinput
echo.
echo Static files collected successfully!
echo.
echo The CSS files should now be available at:
echo - core/static/core/css/workflows_priorities.css
echo.
pause

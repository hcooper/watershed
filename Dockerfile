FROM python:3-slim
WORKDIR /app
COPY sheed.py requirements.txt /app/
COPY static /app/static
RUN pip3 install --no-cache-dir -r requirements.txt
# Prime the python cache
RUN python3 -c "from pysheds.grid import Grid"
EXPOSE 8080
CMD ["python", "sheed.py"]
FROM python:3.12-slim
WORKDIR /app
RUN useradd --uid 10001 --create-home harpoon && mkdir /data && chown harpoon:harpoon /data
COPY server.py prompts.py supervision.py recipe_contract.json /app/
USER harpoon
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
EXPOSE 8080
VOLUME ["/data"]
CMD ["python", "server.py"]

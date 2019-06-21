FROM maiev-base:latest
RUN pip3 install ipython==7.5
COPY ./config.yaml /app/
COPY ./nameko_shell.py /app/
COPY ./completer.py /root/.ipython/profile_default/startup/

ENTRYPOINT  ["/app/nameko_shell.py"]


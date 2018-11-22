FROM maiev-base:latest
RUN pip3 install ipython
COPY ./config.yaml /app/
COPY ./nameko_shell.sh /app
ENTRYPOINT  ["/app/nameko_shell.sh"]


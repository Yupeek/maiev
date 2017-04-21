FROM nginx

ARG text='you '
RUN echo hello you "$text" > /usr/share/nginx/html/index.html
COPY scale_info.sh /usr/bin/scale_info
RUN chmod 755 /usr/bin/scale_info
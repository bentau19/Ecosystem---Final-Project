FROM python:3.13

LABEL authors="Lavi"



WORKDIR /app
COPY . .
VOLUME /windows

RUN chmod +x ./make_exe.sh

ENTRYPOINT ["/bin/bash"]
CMD ["./make_exe.sh"]
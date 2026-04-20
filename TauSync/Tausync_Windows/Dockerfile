FROM mcr.microsoft.com/dotnet/sdk:8.0

LABEL authors="Lavi"


WORKDIR /app
COPY ./TauSync.Lib/ /app/
COPY make_dll.sh .
RUN chmod +x make_dll.sh

VOLUME /output

ENTRYPOINT ["/bin/bash"]
CMD ["make_dll.sh"]





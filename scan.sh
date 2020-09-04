SOURCE_DIR=/Users/tinnvo/Documents/Sources/Release




for PROJECT in $(cat projects.list); do
  echo "START - PREPARING PROJECT ${PROJECT}..."
  PROJECT_PATH=$SOURCE_DIR/${PROJECT}
  sed  "s|PROJECT_PATH|$PROJECT_PATH|" appscan-config.xml > appscan-config-tmp.xml
  cat appscan-config-tmp.xml
  PROJECT_NAME=${PROJECT////_}
  echo "GENERATING ${PROJECT_NAME}.irx..."
  appscan.sh prepare -c appscan-config-tmp.xml -n $PROJECT_NAME.irx
  echo "END - PREPARING PROJECT ${PROJECT}..."

  # echo "START - UPLOADING $PROJECT_NAME.irx FILE..."
  # curl -X POST --header 'Content-Type: multipart/form-data' --header 'Accept: application/json' --header 'Authorization: Bearer <API_KEY>' -F fileName=$PROJECT_NAME.irx 'https://cloud.appscan.com/api/v2/FileUpload'

  echo ""
done

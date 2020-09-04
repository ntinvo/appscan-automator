SOURCE_DIR=/Users/tinnvo/Documents/Sources/Release

PROJECT_ARRAY=("App_Enterprise_Admin" "Application_Addin" "Foundation_Catalog/Catalog" "Foundation_CPQPlatform/CPQPlatform/ariesPorting" "Foundation_CPQPlatform/CPQPlatform/base64" "Foundation_CPQPlatform/CPQPlatform" "Foundation_Delivery/Delivery" "Foundation_CPQPlatform/CPQPlatform/configuredItem" "Foundation_SC_WMS/SC-WMS" "Foundation_CPQPlatform/CPQPlatform/rulesEngine" "Foundation_Order_Orchestration/Order_Orchestration" "Foundation_Deployment_Accelerator/DeploymentAccelerator" "Foundation_IV_Integration/IV_Integration" "Foundation_Inventory/Inventory" "Foundation_JDA_Integration/JDA_Integration" "Foundation_OMPlatform/OMPlatform" "Foundation_Pricing/Pricing" "Foundation_SCWC/SCWC" "Foundation_SC_Platform/FoundationShared" "Foundation_SC_Platform/SC-Platform" "Foundation_VAS/VAS" "Foundation_WMS/WMS" "Foundation_YCS/YCS" "afc.buildutils" "afc.uiproduct/platform_cuf_generator/product" "afc.uiproduct/com.ibm.sterling.afc.restdoc.jspui/product" "afc.uiproduct/platform_afc_ui_impl" "afc.uiproduct/platform_sma_app/product" "afc.uiproduct/platform_uifwk" "afc.uiproduct/platform_uifwk_ide/product")

for PROJECT in ${PROJECT_ARRAY[*]}; do
  echo "PREPARING PROJECT ${PROJECT}..."
  PROJECT_PATH=$SOURCE_DIR/${PROJECT}
  sed  "s|PROJECT_PATH|$PROJECT_PATH|" appscan-config.xml > appscan-config-tmp.xml
  cat appscan-config-tmp.xml
  PROJECT_NAME=${PROJECT////_}
  echo "GENERATING ${PROJECT_NAME}.irx..."
  appscan.sh prepare -c appscan-config-tmp.xml -n $PROJECT_NAME.irx
  echo ""
done

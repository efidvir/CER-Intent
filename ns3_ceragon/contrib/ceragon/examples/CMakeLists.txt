build_lib_example(
  NAME ceragon-twin-from-file
  SOURCE_FILES ceragon-twin-from-file.cc
  LIBRARIES_TO_LINK ${libceragon}
)

build_lib_example(
  NAME ceragon-portfolio-twin
  SOURCE_FILES ceragon-portfolio-twin.cc
  LIBRARIES_TO_LINK ${libceragon}
)

build_lib_example(
  NAME ceragon-multiband-rain
  SOURCE_FILES ceragon-multiband-rain.cc
  LIBRARIES_TO_LINK ${libceragon}
                    ${libapplications}
                    ${libinternet}
)

build_lib_example(
  NAME ceragon-tsn-fronthaul
  SOURCE_FILES ceragon-tsn-fronthaul.cc
  LIBRARIES_TO_LINK ${libceragon}
                    ${libapplications}
                    ${libinternet}
                    ${libflow-monitor}
                    ${libtraffic-control}
)

build_lib_example(
  NAME ceragon-terragraph-mesh
  SOURCE_FILES ceragon-terragraph-mesh.cc
  LIBRARIES_TO_LINK ${libceragon}
)

build_lib_example(
  NAME ceragon-protection-switchover
  SOURCE_FILES ceragon-protection-switchover.cc
  LIBRARIES_TO_LINK ${libceragon}
                    ${libapplications}
                    ${libinternet}
                    ${libflow-monitor}
)

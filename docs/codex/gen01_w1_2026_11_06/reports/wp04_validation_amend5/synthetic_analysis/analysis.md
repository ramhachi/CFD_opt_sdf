# TOPO-2D-00 analysis

Status: **CONCORDANT**.

- No physical, grid-independent, FSAE or 3D qualification is implied.
- Concordance is judged per Re using the required downforce 12/23 intervals, then combined under registration Amendment 5; other sorted-rank interval resolution is descriptive.
- RETENTION_12 uses delta-method relative-increment variances followed by Fieller; it is not an exact nested-ratio interval.
- The uncertainty model treats placement phases and equal-duration batches as sampling units; iid adequacy requires registration review.
- The confirmation grid re-thickens at its own 4dx; its contrast includes geometry and grid changes.
- Thickening-alone differences need the same observable on sharp and thick arms; the primary pressure/total arms cannot be subtracted.

All forces below are dimensionless coefficients on c1 = 223.4 mm. Differences are candidate minus baseline; positive downforce is -Cz and positive drag is +Cx.

## TR-00 qualification

| model/family | result | sharp increment | 90% interval | ratio 90% interval |
| --- | --- | ---: | --- | --- |
| SA-WF/fine30 | TR00_PASS_RATIO | 1.0 | [0.9999999999999999, 1.0000000000000002] | [0.9999999999999999, 1.0000000000000002] |
| SA-WF/second | TR00_PASS_RATIO | 1.0 | [0.9999999999999999, 1.0000000000000002] | [0.9999999999999999, 1.0000000000000002] |
| SST-WF/fine30 | TR00_PASS_RATIO | 1.0 | [0.9999999999999999, 1.0000000000000002] | [0.9999999999999999, 1.0000000000000002] |
| SST-WF/second | TR00_PASS_RATIO | 1.0 | [0.9999999999999999, 1.0000000000000002] | [0.9999999999999999, 1.0000000000000002] |

## WaterLily paired estimates

| Re | contrast | response | mean | sigma A | sigma B | sigma | 90% interval |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1000 | 12 | downforce | 1 | 1.6215845e-16 | 0.00081649658 | 0.00081649658 | [0.9996421600945959, 1.0003578399054045] |
| 1000 | 12 | drag | 0.1 | 1.9950577e-17 | 8.1649658e-05 | 8.1649658e-05 | [0.09996421600945961, 0.10003578399054046] |
| 1000 | 23 | downforce | 1 | 0 | 0.00081649658 | 0.00081649658 | [0.9996421600945957, 1.0003578399054043] |
| 1000 | 23 | drag | 0.1 | 2.0269806e-17 | 8.1649658e-05 | 8.1649658e-05 | [0.09996421600945958, 0.10003578399054043] |
| 3000 | 12 | downforce | 1 | 1.6215845e-16 | 0.00081649658 | 0.00081649658 | [0.9996421600945959, 1.0003578399054045] |
| 3000 | 12 | drag | 0.1 | 1.9950577e-17 | 8.1649658e-05 | 8.1649658e-05 | [0.09996421600945961, 0.10003578399054046] |
| 3000 | 23 | downforce | 1 | 0 | 0.00081649658 | 0.00081649658 | [0.9996421600945957, 1.0003578399054043] |
| 3000 | 23 | drag | 0.1 | 2.0269806e-17 | 8.1649658e-05 | 8.1649658e-05 | [0.09996421600945958, 0.10003578399054043] |

## Qualified RANS cells and worst-case interval envelope

| model/family | contrast | response | mean | 90% interval |
| --- | --- | --- | ---: | --- |
| SA-WF/fine30 | 12 | downforce | 1 | [0.9999999999999999, 1.0000000000000002] |
| SA-WF/fine30 | 12 | drag | 0.1 | [0.1, 0.1] |
| SA-WF/fine30 | 23 | downforce | 1 | [1.0, 1.0] |
| SA-WF/fine30 | 23 | drag | 0.1 | [0.10000000000000002, 0.10000000000000005] |
| SA-WF/second | 12 | downforce | 1 | [0.9999999999999999, 1.0000000000000002] |
| SA-WF/second | 12 | drag | 0.1 | [0.1, 0.1] |
| SA-WF/second | 23 | downforce | 1 | [1.0, 1.0] |
| SA-WF/second | 23 | drag | 0.1 | [0.10000000000000002, 0.10000000000000005] |
| SST-WF/fine30 | 12 | downforce | 1 | [0.9999999999999999, 1.0000000000000002] |
| SST-WF/fine30 | 12 | drag | 0.1 | [0.1, 0.1] |
| SST-WF/fine30 | 23 | downforce | 1 | [1.0, 1.0] |
| SST-WF/fine30 | 23 | drag | 0.1 | [0.10000000000000002, 0.10000000000000005] |
| SST-WF/second | 12 | downforce | 1 | [0.9999999999999999, 1.0000000000000002] |
| SST-WF/second | 12 | drag | 0.1 | [0.1, 0.1] |
| SST-WF/second | 23 | downforce | 1 | [1.0, 1.0] |
| SST-WF/second | 23 | drag | 0.1 | [0.10000000000000002, 0.10000000000000005] |

Worst-case envelopes retain every qualified model/family; they are descriptive envelopes, not pooled confidence intervals. Agreement requires every qualified cell to agree.

- 12 downforce: [1, 1].
- 12 drag: [0.1, 0.1].
- 23 downforce: [1, 1].
- 23 drag: [0.1, 0.1].

## Agreement, resolution, controls and observable diagnostics

```json
{
  "agreement": {
    "1000": {
      "DRAG_SIGN_AGREE_12": true,
      "RANK_AGREE": true,
      "SIGN_AGREE_12": true,
      "cells": {
        "SA-WF/fine30": {
          "DRAG_SIGN_AGREE_12": true,
          "RANK_AGREE": true,
          "RETENTION_12": {
            "fieller": {
              "intervals": [
                [
                  0.8341692150724848,
                  0.8383352560756058
                ]
              ],
              "kind": "bounded"
            },
            "relative_r": 0.996512207274539,
            "relative_w": 0.8333333333333336,
            "variance_r": 7.395912357921604e-07,
            "variance_w": 6.83191872427997e-07
          },
          "SIGN_AGREE_12": true
        },
        "SA-WF/second": {
          "DRAG_SIGN_AGREE_12": true,
          "RANK_AGREE": true,
          "RETENTION_12": {
            "fieller": {
              "intervals": [
                [
                  0.8341692150724848,
                  0.8383352560756058
                ]
              ],
              "kind": "bounded"
            },
            "relative_r": 0.996512207274539,
            "relative_w": 0.8333333333333336,
            "variance_r": 7.395912357921604e-07,
            "variance_w": 6.83191872427997e-07
          },
          "SIGN_AGREE_12": true
        },
        "SST-WF/fine30": {
          "DRAG_SIGN_AGREE_12": true,
          "RANK_AGREE": true,
          "RETENTION_12": {
            "fieller": {
              "intervals": [
                [
                  0.8341692150724848,
                  0.8383352560756058
                ]
              ],
              "kind": "bounded"
            },
            "relative_r": 0.996512207274539,
            "relative_w": 0.8333333333333336,
            "variance_r": 7.395912357921604e-07,
            "variance_w": 6.83191872427997e-07
          },
          "SIGN_AGREE_12": true
        },
        "SST-WF/second": {
          "DRAG_SIGN_AGREE_12": true,
          "RANK_AGREE": true,
          "RETENTION_12": {
            "fieller": {
              "intervals": [
                [
                  0.8341692150724848,
                  0.8383352560756058
                ]
              ],
              "kind": "bounded"
            },
            "relative_r": 0.996512207274539,
            "relative_w": 0.8333333333333336,
            "variance_r": 7.395912357921604e-07,
            "variance_w": 6.83191872427997e-07
          },
          "SIGN_AGREE_12": true
        }
      },
      "state": "CONCORDANT"
    },
    "3000": {
      "DRAG_SIGN_AGREE_12": true,
      "RANK_AGREE": true,
      "SIGN_AGREE_12": true,
      "cells": {
        "SA-WF/fine30": {
          "DRAG_SIGN_AGREE_12": true,
          "RANK_AGREE": true,
          "RETENTION_12": {
            "fieller": {
              "intervals": [
                [
                  0.8341692150724848,
                  0.8383352560756058
                ]
              ],
              "kind": "bounded"
            },
            "relative_r": 0.996512207274539,
            "relative_w": 0.8333333333333336,
            "variance_r": 7.395912357921604e-07,
            "variance_w": 6.83191872427997e-07
          },
          "SIGN_AGREE_12": true
        },
        "SA-WF/second": {
          "DRAG_SIGN_AGREE_12": true,
          "RANK_AGREE": true,
          "RETENTION_12": {
            "fieller": {
              "intervals": [
                [
                  0.8341692150724848,
                  0.8383352560756058
                ]
              ],
              "kind": "bounded"
            },
            "relative_r": 0.996512207274539,
            "relative_w": 0.8333333333333336,
            "variance_r": 7.395912357921604e-07,
            "variance_w": 6.83191872427997e-07
          },
          "SIGN_AGREE_12": true
        },
        "SST-WF/fine30": {
          "DRAG_SIGN_AGREE_12": true,
          "RANK_AGREE": true,
          "RETENTION_12": {
            "fieller": {
              "intervals": [
                [
                  0.8341692150724848,
                  0.8383352560756058
                ]
              ],
              "kind": "bounded"
            },
            "relative_r": 0.996512207274539,
            "relative_w": 0.8333333333333336,
            "variance_r": 7.395912357921604e-07,
            "variance_w": 6.83191872427997e-07
          },
          "SIGN_AGREE_12": true
        },
        "SST-WF/second": {
          "DRAG_SIGN_AGREE_12": true,
          "RANK_AGREE": true,
          "RETENTION_12": {
            "fieller": {
              "intervals": [
                [
                  0.8341692150724848,
                  0.8383352560756058
                ]
              ],
              "kind": "bounded"
            },
            "relative_r": 0.996512207274539,
            "relative_w": 0.8333333333333336,
            "variance_r": 7.395912357921604e-07,
            "variance_w": 6.83191872427997e-07
          },
          "SIGN_AGREE_12": true
        }
      },
      "state": "CONCORDANT"
    }
  },
  "controls": {
    "determinism": {
      "judged": true,
      "pass": true
    },
    "domain": {
      "status": "NOT_JUDGED",
      "z": null
    },
    "manipulation": {
      "R/SA-WF/fine30": {
        "pass": true,
        "z": 1.685092681282319e+16
      },
      "R/SA-WF/second": {
        "pass": true,
        "z": 1.685092681282319e+16
      },
      "R/SST-WF/fine30": {
        "pass": true,
        "z": 1.685092681282319e+16
      },
      "R/SST-WF/second": {
        "pass": true,
        "z": 1.685092681282319e+16
      },
      "W/1000": {
        "pass": true,
        "z": 4898.979485566896
      },
      "W/3000": {
        "pass": true,
        "z": 4898.979485566896
      }
    },
    "readout": {
      "1000": {
        "cur": {
          "downforce": 1.0000000000000002,
          "drag": 0.10000000000000003
        },
        "cv": null,
        "nds": null
      },
      "3000": {
        "cur": {
          "downforce": 1.0000000000000002,
          "drag": 0.10000000000000003
        },
        "cv": null,
        "nds": null
      }
    }
  },
  "height": {
    "h_over_c": 0.2631578947368421,
    "h_over_c1": 0.4476275738585497,
    "height_mm": 100.0
  },
  "observables": {
    "rans_main": "total_cl",
    "tr00": "pressure_cl",
    "waterlily": "total_cl"
  },
  "rans_diagnostics": {
    "SA-WF/fine30": {
      "E1": {
        "ci90": null,
        "distinct_meshes": 8,
        "measured_realisations": 8,
        "point_estimate": {
          "downforce": 1.0035,
          "drag": 0.10035000000000001
        },
        "status": "COMPLETE"
      },
      "E1_sharp": {
        "ci90": null,
        "distinct_meshes": 8,
        "measured_realisations": 8,
        "point_estimate": {
          "downforce": 1.0035,
          "drag": 0.10035000000000001
        },
        "status": "COMPLETE"
      },
      "E2": {
        "ci90": null,
        "distinct_meshes": 8,
        "measured_realisations": 8,
        "point_estimate": {
          "downforce": 2.0035,
          "drag": 0.20035
        },
        "status": "COMPLETE"
      },
      "E2_sharp": {
        "ci90": null,
        "distinct_meshes": 8,
        "measured_realisations": 8,
        "point_estimate": {
          "downforce": 2.0035,
          "drag": 0.20035
        },
        "status": "COMPLETE"
      },
      "E3": {
        "ci90": null,
        "distinct_meshes": 8,
        "measured_realisations": 8,
        "point_estimate": {
          "downforce": 3.0035,
          "drag": 0.30035
        },
        "status": "COMPLETE"
      }
    },
    "SA-WF/second": {
      "E1": {
        "ci90": null,
        "distinct_meshes": 8,
        "measured_realisations": 8,
        "point_estimate": {
          "downforce": 1.0035,
          "drag": 0.10035000000000001
        },
        "status": "COMPLETE"
      },
      "E1_sharp": {
        "ci90": null,
        "distinct_meshes": 8,
        "measured_realisations": 8,
        "point_estimate": {
          "downforce": 1.0035,
          "drag": 0.10035000000000001
        },
        "status": "COMPLETE"
      },
      "E2": {
        "ci90": null,
        "distinct_meshes": 8,
        "measured_realisations": 8,
        "point_estimate": {
          "downforce": 2.0035,
          "drag": 0.20035
        },
        "status": "COMPLETE"
      },
      "E2_sharp": {
        "ci90": null,
        "distinct_meshes": 8,
        "measured_realisations": 8,
        "point_estimate": {
          "downforce": 2.0035,
          "drag": 0.20035
        },
        "status": "COMPLETE"
      },
      "E3": {
        "ci90": null,
        "distinct_meshes": 8,
        "measured_realisations": 8,
        "point_estimate": {
          "downforce": 3.0035,
          "drag": 0.30035
        },
        "status": "COMPLETE"
      }
    },
    "SST-WF/fine30": {
      "E1": {
        "ci90": null,
        "distinct_meshes": 8,
        "measured_realisations": 8,
        "point_estimate": {
          "downforce": 1.0035,
          "drag": 0.10035000000000001
        },
        "status": "COMPLETE"
      },
      "E1_sharp": {
        "ci90": null,
        "distinct_meshes": 8,
        "measured_realisations": 8,
        "point_estimate": {
          "downforce": 1.0035,
          "drag": 0.10035000000000001
        },
        "status": "COMPLETE"
      },
      "E2": {
        "ci90": null,
        "distinct_meshes": 8,
        "measured_realisations": 8,
        "point_estimate": {
          "downforce": 2.0035,
          "drag": 0.20035
        },
        "status": "COMPLETE"
      },
      "E2_sharp": {
        "ci90": null,
        "distinct_meshes": 8,
        "measured_realisations": 8,
        "point_estimate": {
          "downforce": 2.0035,
          "drag": 0.20035
        },
        "status": "COMPLETE"
      },
      "E3": {
        "ci90": null,
        "distinct_meshes": 8,
        "measured_realisations": 8,
        "point_estimate": {
          "downforce": 3.0035,
          "drag": 0.30035
        },
        "status": "COMPLETE"
      }
    },
    "SST-WF/second": {
      "E1": {
        "ci90": null,
        "distinct_meshes": 8,
        "measured_realisations": 8,
        "point_estimate": {
          "downforce": 1.0035,
          "drag": 0.10035000000000001
        },
        "status": "COMPLETE"
      },
      "E1_sharp": {
        "ci90": null,
        "distinct_meshes": 8,
        "measured_realisations": 8,
        "point_estimate": {
          "downforce": 1.0035,
          "drag": 0.10035000000000001
        },
        "status": "COMPLETE"
      },
      "E2": {
        "ci90": null,
        "distinct_meshes": 8,
        "measured_realisations": 8,
        "point_estimate": {
          "downforce": 2.0035,
          "drag": 0.20035
        },
        "status": "COMPLETE"
      },
      "E2_sharp": {
        "ci90": null,
        "distinct_meshes": 8,
        "measured_realisations": 8,
        "point_estimate": {
          "downforce": 2.0035,
          "drag": 0.20035
        },
        "status": "COMPLETE"
      },
      "E3": {
        "ci90": null,
        "distinct_meshes": 8,
        "measured_realisations": 8,
        "point_estimate": {
          "downforce": 3.0035,
          "drag": 0.30035
        },
        "status": "COMPLETE"
      }
    }
  },
  "resolution": {
    "downforce": {
      "confirmation": {
        "ci90": [
          0.9990392434009023,
          1.0009607565990981
        ],
        "df": 3,
        "mean": 1.0000000000000002,
        "n": 4,
        "se": 0.0004082482904638181,
        "sigma": 0.0008164965809276362,
        "sigma_a": 1.8129866073473578e-16,
        "sigma_b": 0.0008164965809276362
      },
      "main": {
        "ci90": [
          0.9990392434009023,
          1.0009607565990981
        ],
        "df": 3,
        "mean": 1.0000000000000002,
        "n": 4,
        "se": 0.0004082482904638181,
        "sigma": 0.0008164965809276362,
        "sigma_a": 1.8129866073473578e-16,
        "sigma_b": 0.0008164965809276362
      },
      "ratio": {
        "intervals": [
          [
            0.9986422071008557,
            1.0013596390073338
          ]
        ],
        "kind": "bounded"
      }
    },
    "status": "PASS"
  },
  "thickening_alone": {
    "SA-WF/fine30": {
      "E1": {
        "from": "E1_sharp",
        "observables": {
          "pressure_cl": {
            "ci90": null,
            "observable": "pressure_cl",
            "paired_realisations": 0,
            "point_estimate": null,
            "status": "UNAVAILABLE"
          },
          "total_cl": {
            "ci90": null,
            "observable": "total_cl",
            "paired_realisations": 0,
            "point_estimate": null,
            "status": "UNAVAILABLE"
          }
        },
        "to": "E1"
      },
      "E2": {
        "from": "E2_sharp",
        "observables": {
          "pressure_cl": {
            "ci90": null,
            "observable": "pressure_cl",
            "paired_realisations": 0,
            "point_estimate": null,
            "status": "UNAVAILABLE"
          },
          "total_cl": {
            "ci90": null,
            "observable": "total_cl",
            "paired_realisations": 0,
            "point_estimate": null,
            "status": "UNAVAILABLE"
          }
        },
        "to": "E2"
      },
      "E3": {
        "observables": {},
        "status": "UNAVAILABLE_SHARP_ARM"
      }
    },
    "SA-WF/second": {
      "E1": {
        "from": "E1_sharp",
        "observables": {
          "pressure_cl": {
            "ci90": null,
            "observable": "pressure_cl",
            "paired_realisations": 0,
            "point_estimate": null,
            "status": "UNAVAILABLE"
          },
          "total_cl": {
            "ci90": null,
            "observable": "total_cl",
            "paired_realisations": 0,
            "point_estimate": null,
            "status": "UNAVAILABLE"
          }
        },
        "to": "E1"
      },
      "E2": {
        "from": "E2_sharp",
        "observables": {
          "pressure_cl": {
            "ci90": null,
            "observable": "pressure_cl",
            "paired_realisations": 0,
            "point_estimate": null,
            "status": "UNAVAILABLE"
          },
          "total_cl": {
            "ci90": null,
            "observable": "total_cl",
            "paired_realisations": 0,
            "point_estimate": null,
            "status": "UNAVAILABLE"
          }
        },
        "to": "E2"
      },
      "E3": {
        "observables": {},
        "status": "UNAVAILABLE_SHARP_ARM"
      }
    },
    "SST-WF/fine30": {
      "E1": {
        "from": "E1_sharp",
        "observables": {
          "pressure_cl": {
            "ci90": null,
            "observable": "pressure_cl",
            "paired_realisations": 0,
            "point_estimate": null,
            "status": "UNAVAILABLE"
          },
          "total_cl": {
            "ci90": null,
            "observable": "total_cl",
            "paired_realisations": 0,
            "point_estimate": null,
            "status": "UNAVAILABLE"
          }
        },
        "to": "E1"
      },
      "E2": {
        "from": "E2_sharp",
        "observables": {
          "pressure_cl": {
            "ci90": null,
            "observable": "pressure_cl",
            "paired_realisations": 0,
            "point_estimate": null,
            "status": "UNAVAILABLE"
          },
          "total_cl": {
            "ci90": null,
            "observable": "total_cl",
            "paired_realisations": 0,
            "point_estimate": null,
            "status": "UNAVAILABLE"
          }
        },
        "to": "E2"
      },
      "E3": {
        "observables": {},
        "status": "UNAVAILABLE_SHARP_ARM"
      }
    },
    "SST-WF/second": {
      "E1": {
        "from": "E1_sharp",
        "observables": {
          "pressure_cl": {
            "ci90": null,
            "observable": "pressure_cl",
            "paired_realisations": 0,
            "point_estimate": null,
            "status": "UNAVAILABLE"
          },
          "total_cl": {
            "ci90": null,
            "observable": "total_cl",
            "paired_realisations": 0,
            "point_estimate": null,
            "status": "UNAVAILABLE"
          }
        },
        "to": "E1"
      },
      "E2": {
        "from": "E2_sharp",
        "observables": {
          "pressure_cl": {
            "ci90": null,
            "observable": "pressure_cl",
            "paired_realisations": 0,
            "point_estimate": null,
            "status": "UNAVAILABLE"
          },
          "total_cl": {
            "ci90": null,
            "observable": "total_cl",
            "paired_realisations": 0,
            "point_estimate": null,
            "status": "UNAVAILABLE"
          }
        },
        "to": "E2"
      },
      "E3": {
        "observables": {},
        "status": "UNAVAILABLE_SHARP_ARM"
      }
    }
  }
}
```

## Provenance

```json
{
  "evidence_class": "SYNTHETIC_SOFTWARE_ONLY",
  "note": "Planted forces and Cp; no CFD, no study freeze, no physical concordance result",
  "source_sha256": {
    "scripts/topo2d00/analyze.py": "846ad882a65e108004d48e350ade054304adc19f02bcfad029b127b7b7eb5893",
    "scripts/topo2d00/check.py": "4c3e63092158db4d1338739ffb4f15b91c1ff577fbea2abde7b6043759d23374"
  }
}
```

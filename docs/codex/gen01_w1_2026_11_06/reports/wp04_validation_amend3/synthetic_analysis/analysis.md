# TOPO-2D-00 analysis

Status: **CONCORDANT**.

- No physical, grid-independent, FSAE or 3D qualification is implied.
- CONCORDANT_PARTIAL requires registration clarification: Amendment 3's exactly-one-Re rule is unreachable under earlier global UNRESOLVED and resolved-rank DISCORDANT precedence.
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

| Re | contrast | response | mean | sigma A | sigma B | sigma upper | 90% interval |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1000 | 12 | downforce | 1 | 1.6215845e-16 | 0.00081649658 | 0.009854411 | [0.9956811803096468, 1.0043188196903536] |
| 1000 | 12 | drag | 0.1 | 1.9950577e-17 | 8.1649658e-05 | 0.0009854411 | [0.09956811803096466, 0.10043188196903541] |
| 1000 | 23 | downforce | 1 | 0 | 0.00081649658 | 0.009854411 | [0.9956811803096466, 1.0043188196903534] |
| 1000 | 23 | drag | 0.1 | 2.0269806e-17 | 8.1649658e-05 | 0.0009854411 | [0.09956811803096466, 0.10043188196903535] |
| 3000 | 12 | downforce | 1 | 1.6215845e-16 | 0.00081649658 | 0.009854411 | [0.9956811803096468, 1.0043188196903536] |
| 3000 | 12 | drag | 0.1 | 1.9950577e-17 | 8.1649658e-05 | 0.0009854411 | [0.09956811803096466, 0.10043188196903541] |
| 3000 | 23 | downforce | 1 | 0 | 0.00081649658 | 0.009854411 | [0.9956811803096466, 1.0043188196903534] |
| 3000 | 23 | drag | 0.1 | 2.0269806e-17 | 8.1649658e-05 | 0.0009854411 | [0.09956811803096466, 0.10043188196903535] |

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
                  0.8303285472889194,
                  0.8421759238591713
                ]
              ],
              "kind": "bounded"
            },
            "relative_r": 0.996512207274539,
            "relative_w": 0.8333333333333336,
            "variance_r": 7.395912357921604e-07,
            "variance_w": 9.190645754784523e-06
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
                  0.8303285472889194,
                  0.8421759238591713
                ]
              ],
              "kind": "bounded"
            },
            "relative_r": 0.996512207274539,
            "relative_w": 0.8333333333333336,
            "variance_r": 7.395912357921604e-07,
            "variance_w": 9.190645754784523e-06
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
                  0.8303285472889194,
                  0.8421759238591713
                ]
              ],
              "kind": "bounded"
            },
            "relative_r": 0.996512207274539,
            "relative_w": 0.8333333333333336,
            "variance_r": 7.395912357921604e-07,
            "variance_w": 9.190645754784523e-06
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
                  0.8303285472889194,
                  0.8421759238591713
                ]
              ],
              "kind": "bounded"
            },
            "relative_r": 0.996512207274539,
            "relative_w": 0.8333333333333336,
            "variance_r": 7.395912357921604e-07,
            "variance_w": 9.190645754784523e-06
          },
          "SIGN_AGREE_12": true
        }
      }
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
                  0.8303285472889194,
                  0.8421759238591713
                ]
              ],
              "kind": "bounded"
            },
            "relative_r": 0.996512207274539,
            "relative_w": 0.8333333333333336,
            "variance_r": 7.395912357921604e-07,
            "variance_w": 9.190645754784523e-06
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
                  0.8303285472889194,
                  0.8421759238591713
                ]
              ],
              "kind": "bounded"
            },
            "relative_r": 0.996512207274539,
            "relative_w": 0.8333333333333336,
            "variance_r": 7.395912357921604e-07,
            "variance_w": 9.190645754784523e-06
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
                  0.8303285472889194,
                  0.8421759238591713
                ]
              ],
              "kind": "bounded"
            },
            "relative_r": 0.996512207274539,
            "relative_w": 0.8333333333333336,
            "variance_r": 7.395912357921604e-07,
            "variance_w": 9.190645754784523e-06
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
                  0.8303285472889194,
                  0.8421759238591713
                ]
              ],
              "kind": "bounded"
            },
            "relative_r": 0.996512207274539,
            "relative_w": 0.8333333333333336,
            "variance_r": 7.395912357921604e-07,
            "variance_w": 9.190645754784523e-06
          },
          "SIGN_AGREE_12": true
        }
      }
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
        "z": 405.9095959963823
      },
      "W/3000": {
        "pass": true,
        "z": 405.9095959963823
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
          0.9927183099506717,
          1.0072816900493287
        ],
        "df": 3,
        "mean": 1.0000000000000002,
        "n": 4,
        "se": 0.0030941629931212633,
        "sigma": 0.0008164965809276362,
        "sigma_a": 1.8129866073473578e-16,
        "sigma_a_upper": 6.759806275937174e-16,
        "sigma_b": 0.0008164965809276362,
        "sigma_b_upper": 0.006188325986242527,
        "sigma_upper": 0.006188325986242527
      },
      "main": {
        "ci90": [
          0.9927183099506717,
          1.0072816900493287
        ],
        "df": 3,
        "mean": 1.0000000000000002,
        "n": 4,
        "se": 0.0030941629931212633,
        "sigma": 0.0008164965809276362,
        "sigma_a": 1.8129866073473578e-16,
        "sigma_a_upper": 6.759806275937174e-16,
        "sigma_b": 0.0008164965809276362,
        "sigma_b_upper": 0.006188325986242527,
        "sigma_upper": 0.006188325986242527
      },
      "ratio": {
        "intervals": [
          [
            0.9897547514581595,
            1.0103513001849667
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
{}
```

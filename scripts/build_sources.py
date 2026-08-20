import pandas as pd

sources = [

    {
        "source": "TrustHub",
        "url": "",
        "category": "Benchmark",
        "status": "Pending"
    },

    {
        "source": "RISCV-Web3",
        "url": "",
        "category": "Benchmark",
        "status": "Pending"
    },

    {
        "source": "OpenTitan",
        "url": "https://github.com/lowRISC/opentitan",
        "category": "Clean",
        "status": "Downloaded"
    },

    {
        "source": "Ibex",
        "url": "https://github.com/lowRISC/ibex",
        "category": "Clean",
        "status": "Downloaded"
    },

    {
        "source": "PicoRV32",
        "url": "https://github.com/YosysHQ/picorv32",
        "category": "Clean",
        "status": "Downloaded"
    },

    {
        "source": "SERV",
        "url": "https://github.com/olofk/serv",
        "category": "Clean",
        "status": "Downloaded"
    },

    {
        "source": "ZipCPU",
        "url": "https://github.com/ZipCPU/zipcpu",
        "category": "Clean",
        "status": "Downloaded"
    },

    {
        "source": "VexRiscv",
        "url": "https://github.com/SpinalHDL/VexRiscv",
        "category": "Clean",
        "status": "Downloaded"
    }

]

df = pd.DataFrame(sources)

df.to_csv("../sources.csv", index=False)

print(df)
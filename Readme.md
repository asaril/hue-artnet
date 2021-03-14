# hue-artnet: python Art-Net to Hue Entertainment converter

## Disclaimer

This is a personal project, just for fun. It is neither clean, nor efficient, nor guaranteed to work without tinkering.
Please be careful when using this to create flashing lights, as this could trigger epileptic symptoms.

## Prerequisites

- Python 3 (tested with 3.7.2)
- python-mbedtls (see below)
- Hue bridge v2 with at least api version 1.22
- Up to 10 Hue Entertainment-compatible lights in one group

### Building python-mbedtls for Windows

python-mbedtls is currently not available as prebuilt package for Windows in pip.
This will probably change in the future, as the maintainer is working on a CI pipeline to provide python wheels
in upcoming releases.
Also, a small patch in mbedtls is required, as the check they use is not valid on Windows (the value for 
FD_SETSIZE cannot be easily determinted, as it depends on the value used to build the Python sockets module, end even
that seems not to be correct). Disabling the check should _only_ be done on Windows!

Building can be done with e.g. VS 2019 Community.

First, get and build mbedtls:
1. Clone mbedtls (I used v2.26.0 from https://github.com/ARMmbed/mbedtls)
2. Patch the socket check for Windows with the patch below
3. Build with CMake in a VSDevCmd shell: 
  - `cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=build_install`
  - `cmake --build build --target install`

```diff
diff --git a/library/net_sockets.c b/library/net_sockets.c
index ad1ac13fb..bc3b12b95 100644
--- a/library/net_sockets.c
+++ b/library/net_sockets.c
@@ -595,8 +595,8 @@ int mbedtls_net_recv_timeout( void *ctx, unsigned char *buf,
      * that are strictly less than FD_SETSIZE. This is a limitation of the
      * fd_set type. Error out early, because attempting to call FD_SET on a
      * large file descriptor is a buffer overflow on typical platforms. */
-    if( fd >= FD_SETSIZE )
-        return( MBEDTLS_ERR_NET_POLL_FAILED );
+    // if( fd >= FD_SETSIZE )
+    //     return( MBEDTLS_ERR_NET_POLL_FAILED );
```

Then get and build python-mbedtls:
1. Clone python-mbedtls (master from https://github.com/Synss/python-mbedtls)
2. Set the env variables INCLUDE and LIBPATH to the just-built mbedtls:
  - `set INCLUDE=..\mbedtls\build_install\include`
  - `set LIBPATH=..\mbedtls\build_install\lib`
3. Build python-mbedtls: `python setup.py install`


## Usage

Copy and adapt the config.json.
To get the required login credentials for your Hue bridge, you can use the login.py script.
Press the link button before running the script, and enter the bridge's IP to fetch a username/key pair.

Each Hue light can be configured onto any DMX channel block of one DMX universe. The mapping can be configured in the
`mapping` list. Each entry should consist of:

```json
{"start": 1, "light": 38, "fine":True}
```

- `start` denotes the lowest DMX channel this light will use
- `light` is the light ID in the Hue system
- `fine` will use two DMX channels per color (RRGGBB), coarse/fine. Optional, defaults to `False`

Hue lights will not support the full 16 bits, in my tests using only one channel per color was enough.

In normal mode, each light will use three DMX channels for the R,G,B, starting with R at the channel given by `start`.
DMX channels are numbered starting from 1.

To facilitate matching the light IDs, run the script without a mapping defined in the config (but valid credentials and
Entertainment group name). It will then cycle through the lights in the given group, and blink the corresponding light.

The script will wait for Art-Net packets to arrive on the configured address. If the stream stops after the first
packet was received, the script will shutdown and exit. You can also abort the script with Ctrl+C and it will try to
shutdown the Hue connection before exiting.

## Restrictions / Caveats

- Supports one Entertainment group on one bridge
- Supports one Art-Net Universe

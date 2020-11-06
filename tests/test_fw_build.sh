#!/bin/bash
cd ../hardware/victims/firmware/simpleserial-aes

#PLAT="CW308_STM32F3"
#CRYPT="TINYAES128C MBEDTLS"
function test()
{
    local -n PLAT=$1
    local -n CRYPT=$2
    local -n OPTS=$3
    local -n SSVER=$4
    for j in "${PLAT[@]}"; do
        for i in "${CRYPT[@]}"; do
            for k in "${OPTS[@]}"; do 
                for l in "${SSVER[@]}"; do
                    make PLATFORM=$j CRYPTO_TARGET=$i CRYPTO_OPTIONS=$k SS_VER=$l
                    retVal=$?
                    make PLATFORM=$j CRYPTO_TARGET=$i CRYPTO_OPTIONS=$k SS_VER=$l clean
                    echo $retVal
                    if [ $retVal -ne 0 ]; then
                        echo "Firmware build failed"
                        exit $retVal
                    fi
                done
            done
        done
    done
}

x=("CWLITEARM" "CWNANO" "CW308_STM32F0" "CW308_STM32F2" "CW308_STM32F1" "CW308_STM32F3" "CW308_STM32F4" "CW308_STM32L4" \
"CW308_STM32L5" "CW308_K82F" "CW308_K24F" "CW308_SAM4L" "CW308_SAML11" "CW308_EFM32TG11B" "CW308_EFR32MG21A")
y=("TINYAES128C" "MBEDTLS")
z=("AES128C")
sver=("SS_VER_2_0" "SS_VER_1_1")

test x y z sver

x=("CW308_STM32F4" "CW308_STM32L4" \
"CW308_STM32L5" "CW308_K24F" "CW308_SAM4L" "CW308_SAML11" "CW308_EFM32TG11B" "CW308_EFR32MG21A")
y=("HWAES")

test x y z sver

x=("CW308_K82F")
y=("HWAES")
z=("MMCAU" "LTC")

test x y z sver

x=("CWLITEXMEGA" "CW304")
y=("TINYAES128C" "AVRCRYPTOLIB")
z=("AES128C")

test x y z sver

x=("CWLITEXMEGA")
y=("MASKEDAES")
z=("VERSION1" "VERSION2")

test x y z sver

echo "All tests okay"
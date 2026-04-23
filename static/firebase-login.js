'use strict'

import { initializeApp } from "https://www.gstatic.com/firebasejs/12.12.0/firebase-app.js";
import { getAuth, createUserWithEmailAndPassword, signInWithEmailAndPassword, signOut } from "https://www.gstatic.com/firebasejs/12.12.0/firebase-auth.js";

const firebaseConfig = {
    apiKey: "AIzaSyAml1-ib60cZsBLk1ggzGvu486cjsdterY",
    authDomain: "a1-3195197.firebaseapp.com",
    projectId: "a1-3195197",
    storageBucket: "a1-3195197.firebasestorage.app",
    messagingSenderId: "129527625723",
    appId: "1:129527625723:web:07b226c2ebc440edf57d5e",
    measurementId: "G-ZZCQNCVP4G"
};

window.addEventListener("load", function() {
    const app = initializeApp(firebaseConfig)
    const auth = getAuth()
    updateUI(document.cookie)
    console.log("hello world load")

    document.getElementById("sign-up").addEventListener('click', function() {
        const email = document.getElementById("email").value
        const password = document.getElementById("password").value

        createUserWithEmailAndPassword(auth, email, password)
        .then((userCredential) => {
            const user = userCredential.user
            user.getIdToken().then((token) => {
                document.cookie = "token=" + token + ";path=/;SameSite=Strict";
                window.location = "/";
            });
        })
        .catch((error) => {
            console.log(error.code + error.message)
        });
    })

    document.getElementById("login").addEventListener('click', function() {
        const email = document.getElementById("email").value
        const password = document.getElementById("password").value

        signInWithEmailAndPassword(auth, email, password)
        .then((userCredential) => {
            const user = userCredential.user
            console.log("logged in")
            user.getIdToken().then((token) => {
                document.cookie = "token=" + token + ";path=/;SameSite=Strict";
                window.location = "/"
            });
        })
        .catch((error) => {
            console.log(error.code + error.message)
        });
    })

    document.getElementById("sign-out").addEventListener('click', function() {
        signOut(auth)
        .then((output) => {
            document.cookie = "token=;path=/;SameSite=Strict";
            window.location = "/";
        })
    })
})

function updateUI(cookie) {
    var token = parseCookieToken(cookie);

    if (token.length > 0) {
        document.getElementById("login-box").hidden = true;
        document.getElementById("sign-out").hidden = false;
    } else {
        document.getElementById("login-box").hidden = false;
        document.getElementById("sign-out").hidden = true;
    }
}

function parseCookieToken(cookie) {
    var strings = cookie.split(';');
    for (let i = 0; i < strings.length; i++) {
        var temp = strings[i].split('=');
        if (temp[0] == "token")
            return temp[1];
    }
    return ""
}
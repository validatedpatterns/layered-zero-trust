# Secure Multi-tier Application Use Case

One of the most common application design patterns makes use of a frontend application leveraging a database for persistent storage. Instead of traditional methods for accessing the database from the frontend application using static values stored within the application, this pattern will make use "just in time" methods for obtaining these database values from a credential store. A more detailed overview is located below:

* qtodo - [Quarkus](https://quarkus.io) based frontend application. Access is protected via OIDC based authentication with users defined within an external identity store (Red Hat Build of Keycloak by default)
* PostgreSQL - Relational database for use by the qtodo application. Credentials are generated dynamically and stored within Vault.
* External Identity store - Users have been defined to enable access to the qtodo frontend. OIDC clients have also been created and configured within the todo application
* HashiCorp Vault - Several features are being leveraged within this use case the external identity store
  * Secrets store - Storage of sensitive values for components including PostgreSQL and RHBK
  * JWT based authentication - Enables access using ZTWIM based identities
* Zero Trust Workload Identity - Enables an identity to be assigned to the qtodo application to communicate with HashiCorp Vault and obtain the credentials to access the PostgreSQL database
  * [spiffe-helper](https://github.com/spiffe/spiffe-helper) - Supplemental component provided for the qtodo application to dynamically fetch JWT based identities from the SPIFFE Workload API.

## Investigating the qtodo Application in depth

With an understanding of the goals and architecture of qtodo, launch the OpenShift Console of the Hub cluster and navigate to the `qtodo` project

1. Select **Home** -> **Projects** from the left hand navigation bar
2. Locate and select the **qtodo** project

The _qtodo_ Quarkus application and _qtodo-db_ PostgreSQL database are found within this namespace.

View the running pods associated with these components

1. Select **Workloads** -> **Pods** from the left hand navigation bar
2. Explore both the _qtodo_ and _qtodo-db_ pods.

Take note that the _qtodo_ Pod makes use of a series of init containers and sidecar containers that are used to supply the application with credentials needed to support the application.

Access the qtodo application in a browser. The URL can be located from the OpenShift Route in the `qtodo` Project

1. Select **Networking** -> **Routes** from the lefthand navigation bar
2. Click the arrow next to the the URL underneath the _Location_ column to open the qtodo application in a new browser tab

You will be presented with a login page to access the application. When using the default External Identity Provider (RHBK), two users (`qtodo-admin` and `qtodo-user`) were provisioned automatically. Their initial credentials are stored in a Secret in the `keycloak-system` namespace called `keycloak-users`. You can reveal the credentials by switching to the tab containing the OpenShift Console using the following steps:

1. Select **Home** -> **Projects** from the left hand navigation bar
2. Locate and select the **keycloak-system** project
3. Select **Workloads** -> **Secrets** from the left hand navigation bar
4. Select the **keycloak-users** Secret
5. Click the **Reveal values** link to uncover the underlying values for the users

Switch back to the qtodo application and enter the username and password on the login page for one of the users using the values discovered previously.

Once you have authenticated to RHBK, you will be instructed to change the temporary password and set a more permanent password. Once complete, you will be redirected to the qtodo application verifying the OIDC based authentication functions properly.

Feel free to add new items to the list of todos. By being able to add and remove items from the page, the integration between the Quarkus application and the backend PostgreSQL database using credentials sourced from HashiCorp Vault was successful.

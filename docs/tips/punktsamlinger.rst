.. _punktsamlinger:

Arbejde med højdetidsserier og punktsamlinger i FIRE
====================================================
En højdetidsserie er en samling af koter, som alle er målt til det samme punkt, og som er
givet i det samme *højdesystem*. Når hver kote i tidsserien er beregnet ved fastholdelse
af det samme punkt med samme kote kaldes koterne i tidsserien for *jessenkoter* og
tidsseriens højdesystem siges at være et *lokalt højdesystem*. Det fastholdte punkt kaldes
for *jessenpunktet* og jessenpunktets fastholdte kote kaldes *referencekoten*.

En samling af højdetidsserier, som alle har samme jessenpunkt og referencekote, kaldes en
*punktsamling* eller *punktgruppe*.

.. note::
    Vær opmærksom at højdetidsseriernes jessenkoter ofte bare kaldes koter. Tilsvarende kaldes
    referencekoten ofte bare for *jessenkoten*!

Arbejdet med højdetidsserier kan inddeles i kategorierne vedligehold og analyse.
Tilsvarende findes der workflows i FIRE som understøtter disse arbejdsopgaver. De følgende
afsnit gennemgår disse to kategorier.

Arbejdet med højdetidsserier ligger i FIREs ``niv``-modul.


Vedligehold af punktsamling indebærer:
- at oprette og lukke


.. _ts_vedligehold:
Vedligehold af punktsamlinger og tidsserier
-------------------------------------------

Vedligehold vil sige at



Opret ny punktsamling
-----------------------
* Opret ny sag og tilhørende sagsark

.. code-block::

    fire niv opret-sag MIN_SAG

* Opret punktsamling i sagsarket og rediger oplysningerne

.. code-block::

    fire niv opret-punktsamling MIN_SAG --jessenpunkt 81999

.. note::
    Hvis jessenpunktet ikke har et jessennummer skal det oprettes først. Se :ref:`opret_jessenpunkt`.

Der oprettes herefter to nye faner i sagsarket: **Punktgruppe** og **Højdetidsserier**.
Oplysningerne i de to faner redigeres indtil man er klar til at lægge dem i databasen.

* Rediger punktgruppe-fanen

  Det er muligt at redigere i punktgruppenavnet og formål. Det anbefales dog at beholde
  default-navnet ``Punktsamling_81xxx``

  .. image:: images/opret_punktgruppe_før.png

  .. image:: images/opret_punktgruppe_efter.png

* Rediger højdetidsserier-fanen

  Den første tidsserie tilhører jessenpunktet og oprettes i arket automatisk. Per
  definition er den konstant (den indeholder kun referencekoten), og er som sådan ret
  intetsigende. Dog er den af tekniske årsager nødvendig.

  .. image:: images/opret_højdetidsserie_før.png

  * Tilføj de ønskede punkter. Husk at angive punktgruppen i første kolonne.
  * Giv tidsserierne et sigende navn. Det anbefales kraftigt at bruge default-formen
    ``<ident>_HTS_<jessennummer>``

  .. image:: images/opret_højdetidsserie_efter.png

.. tip::
    | For at spare lidt tid med at indtaste værdierne i højdetidsserier-fanen kan man med
      fordel bruge ``--punkter`` valgmuligheden:

    .. code-block::

        fire niv opret-punktsamling MIN_SAG --jessenpunkt 81999 --punkter SKEJ,RDIO,RDO1

    | hvilket resulterer i flg:

    .. image:: images/opret_højdetidsserie_tip.png

    | Dette virker også med udtræk af punktsamlinger:

    .. code-block::

        fire niv udtræk-punksamling MIN_SAG --jessenpunkt 81999 --punkter SKEJ,RDIO,RDO1

* Til sidst lægges punktsamling og højdetidsserier i databasen::

      fire niv ilæg-punktsamling MIN_SAG
      fire niv ilæg-tidsserie MIN_SAG

.. _opret_jessenpunkt:
Opret nyt jessennummer
.......................
Før et punkt kan blive brugt som jessenpunkt, skal punktet have et jessennummer. Dette
gøres ved at indsætte attributten ``NET:jessen`` og angive det nye jessennummer med
``IDENT:jessen`` via de gængse kommandoer ``fire niv udtræk-revision`` og ``fire niv
ilæg-revision``.


Rediger eksisterende punktsamlinger og tidsserier
-------------------------------------------------
Der er begrænset mulighed for at redigere databasens oplysninger om en punktsamling, idet kun formålet kan redigeres.
Idet det antages at der er oprettet en sag i forvejen, gøres følgende::

    fire niv udtræk-punktsamling MIN_SAG PUNKTSAMLING_81999
    >> Rediger formål for punktsamlinger og tidsserier i sagsarket
    fire niv ilæg-punktsamling MIN_SAG
    fire niv ilæg-tidsserie MIN_SAG

Tilføje punkt til punktsamling
------------------------------



Opdatering af højdetidsserier
-----------------------------


Opdatering



Skift af jessenpunkt
--------------------
Sommetider er det nødvendigt at udskifte jessenpunktet for en punktsamling. Enten fordi
jessenpunktet konstateres ustabilt, jessenpunktet er gået tabt eller anden årsag.

Der findes to måder at dette kan udføres på: en quick'n'dirty (transformation) og en stringent (genberegning).


Quick'N'Dirty
.............
Den hurtige og beskidte metode er til hurtige ad hoc beregninger eller analyser, hvor man
"transformerer" tidsseriekoterne fra det gamle, lokale højdesystem til det nye højdesystem.

Dette er fx praktisk i tilfældet hvor to tidsserier har forskellige bevægelser ift.
jessenpunktet. Her kan det være svært rent grafisk at anskue de to punkters bevægelse ift.
hinanden, hvorfor det kan hjælpe at ophøje det ene punkt til jessenpunkt, hvis bevægelse i
sit eget system pr. definition er 0.

Der tages udgangspunkt i den "gamle" tidsserie for det punkt som skal være det nye
jessenpunkt. *Denne tidsserie trækkes simpelthen bare fra de andre tidsserier i
punktsamlingen*. Dette kræver at tidsserierne er beregnet til de samme tidspunkter som det
nye jessenpunkt.

 Denne operation er faktisk ikke *så* dirty, idet det faktisk giver de samme koter som
 hvis man lavede en genberegning med et nyt fastholdt jessenpunkt. Dog vil de estimerede
 spredninger ikke blive transformeret, hvorfor denne metode ikke bør anvendes til
 tidsserier som skal lægges i databasen.

.. note::

    Dette er pt. ikke implementeret i FIRE. Vil man anvende denne metode kan det relativt
    let gøres ved at udtrække de tidsserier man er interesseret i med ``fire ts hts``, og
    derefter selv trække tidsserierne fra hinanden, eksempelvis i excel.

.. tip::

    Vil man være endnu mere dirty, så kan man interpolere imellem
    tidspunkterne i det nye jessenpunkts tidsserie for at kunne transformere data til de
    tidspunkter hvor tidsserien for det nye jessenpunkt ikke er blevet beregnet.

Den stringente
..............

I FIREs datamodel, er jessenpunktet definerende for en punktsamling, og derfor kan man
principielt ikke *skifte* jessenpunktet. Dog er det muligt at oprette en ny punktsamling
med det nye jessenpunkt, og som indeholder de samme punkter som den gamle punktsamling.

Derefter er det nødvendigt at genberegne tidsserierne, skridt for skridt, og ved hvert
skridt anvende det samme sæt af observationer som blev brugt til de gamle tidsserier, og
selvfølgelig med fastholdelse af det nye jessenpunkt.

For at kunne genskabe alle tidsskridt i de gamle tidsserier kræves at det nye jessenpunkt
har været opmålt i de samme kampagner som det gamle jessenpunkt.

**Fremgangsmåde:**

#. Giv nyt jessenpunkt et jessennummer med ``fire niv udtræk-revision`` og ``fire niv ilæg-revision``
#. Opret ny punktsamling med det nye jessenpunkt
#. Tilføj punkter og tidsserier til punktsamlingen
#. For hver tidspunkt i de gamle tidsserier:
    - Udtræk relevante observationer
    - Følg det gængse niv-workflow for beregning og ilægning af tidsseriekoter, som
      beskrevet i **INDSÆT REFERENCE**

.. tip::

    Step 2-3 gøres nemmest ved at udtrække den gamle punktsamling med ``fire niv
    udtræk-punktsamling`` og derefter redigere jessenpunkt, punktsamlingsnavn og formål og ilægge
    med ``fire niv ilæg-punktsamling``


.. list-table:: Opmålingstidsspunkt
   :widths: 25 25 50
   :header-rows: 1

   * - Heading row 1, column 1
     - Heading row 1, column 2
     - Heading row 1, column 3
   * - Row 1, column 1
     -
     - Row 1, column 3
   * - Row 2, column 1
     - Row 2, column 2
     - Row 2, column 3
Jessenpunkt  x
A            - - - - - - - - -
B




Analyse af højdetidsserier
--------------------------
Man bruger programmet :ref:`fire_ts_analyse-gnss:` til at analysere GNSS-tidsserier.
Programmet kan blabla


MUSPI MEROL
...........
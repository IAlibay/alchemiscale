from datetime import datetime, timedelta
import random
from time import sleep
from typing import List, Dict
from pathlib import Path

import pytest
from gufe import AlchemicalNetwork
from gufe.tokenization import TOKENIZABLE_REGISTRY
from gufe.protocols.protocoldag import execute_DAG, ProtocolDAG, ProtocolDAGResult

from alchemiscale.storage.statestore import Neo4jStore
from alchemiscale.storage.models import (
    Task,
    TaskHub,
    ProtocolDAGResultRef,
    TaskStatusEnum,
    ComputeServiceID,
    ComputeServiceRegistration,
)
from alchemiscale.models import Scope, ScopedKey
from alchemiscale.security.models import (
    CredentialedEntity,
    CredentialedUserIdentity,
    CredentialedComputeIdentity,
)
from alchemiscale.security.auth import hash_key


class TestStateStore:
    ...


class TestNeo4jStore(TestStateStore):
    ...

    @pytest.fixture
    def n4js(self, n4js_fresh):
        return n4js_fresh

    def test_server(self, graph):
        graph.service.system_graph.call("dbms.security.listUsers")

    ### gufe object handling

    def test_create_network(self, n4js, network_tyk2, scope_test):
        an = network_tyk2

        sk: ScopedKey = n4js.create_network(an, scope_test)

        out = n4js.graph.run(
            f"""
                match (n:AlchemicalNetwork {{_gufe_key: '{an.key}', 
                                             _org: '{sk.org}', _campaign: '{sk.campaign}', 
                                             _project: '{sk.project}'}}) 
                return n
                """
        )
        n = out.to_subgraph()

        assert n["name"] == "tyk2_relative_benchmark"

    def test_create_overlapping_networks(self, n4js, network_tyk2, scope_test):
        an = network_tyk2

        sk: ScopedKey = n4js.create_network(an, scope_test)

        n = n4js.graph.run(
            f"""
                match (n:AlchemicalNetwork {{_gufe_key: '{an.key}', 
                                             _org: '{sk.org}', _campaign: '{sk.campaign}', 
                                             _project: '{sk.project}'}}) 
                return n
                """
        ).to_subgraph()

        assert n["name"] == "tyk2_relative_benchmark"

        # add the same network twice
        sk2: ScopedKey = n4js.create_network(an, scope_test)
        assert sk2 == sk

        n2 = n4js.graph.run(
            f"""
                match (n:AlchemicalNetwork {{_gufe_key: '{an.key}', 
                                             _org: '{sk.org}', _campaign: '{sk.campaign}', 
                                             _project: '{sk.project}'}}) 
                return n
                """
        ).to_subgraph()

        assert n2["name"] == "tyk2_relative_benchmark"
        assert n2.identity == n.identity

        # add a slightly different network
        an2 = AlchemicalNetwork(
            edges=list(an.edges)[:-1], name="tyk2_relative_benchmark_-1"
        )
        sk3 = n4js.create_network(an2, scope_test)
        assert sk3 != sk

        n3 = n4js.graph.run(
            f"""
                match (n:AlchemicalNetwork) 
                return n
                """
        ).to_subgraph()

        assert len(n3.nodes) == 2

    def test_delete_network(self):
        ...

    def test_get_network(self, n4js, network_tyk2, scope_test):
        an = network_tyk2
        sk: ScopedKey = n4js.create_network(an, scope_test)

        an2 = n4js.get_gufe(sk)

        assert an2 == an
        assert an2 is an

        TOKENIZABLE_REGISTRY.clear()

        an3 = n4js.get_gufe(sk)

        assert an3 == an2 == an

    def test_query_networks(self, n4js, network_tyk2, scope_test, multiple_scopes):
        an = network_tyk2
        an2 = AlchemicalNetwork(edges=list(an.edges)[:-2], name="incomplete")

        sk: ScopedKey = n4js.create_network(an, scope_test)
        sk2: ScopedKey = n4js.create_network(an2, scope_test)

        an_sks: List[ScopedKey] = n4js.query_networks()

        assert sk in an_sks
        assert sk2 in an_sks
        assert len(an_sks) == 2

        # test scopes query
        an_sks = n4js.query_networks(scope=scope_test)
        assert len(an_sks) == 2

        an_sks = n4js.query_networks(scope=multiple_scopes[1])
        assert len(an_sks) == 0

        # test name query
        an_sks = n4js.query_networks(name="tyk2_relative_benchmark")
        assert len(an_sks) == 1

    def test_query_transformations(self, n4js, network_tyk2, multiple_scopes):
        an = network_tyk2

        sk: ScopedKey = n4js.create_network(an, multiple_scopes[0])
        sk2: ScopedKey = n4js.create_network(an, multiple_scopes[1])

        transformation_sks = n4js.query_transformations()

        assert len(transformation_sks) == len(network_tyk2.edges) * 2
        assert len(n4js.query_transformations(scope=multiple_scopes[0])) == len(
            network_tyk2.edges
        )
        assert (
            len(n4js.query_transformations(name="lig_ejm_31_to_lig_ejm_50_complex"))
            == 2
        )
        assert (
            len(
                n4js.query_transformations(
                    scope=multiple_scopes[0], name="lig_ejm_31_to_lig_ejm_50_complex"
                )
            )
            == 1
        )

    def test_query_chemicalsystems(self, n4js, network_tyk2, multiple_scopes):
        an = network_tyk2

        sk: ScopedKey = n4js.create_network(an, multiple_scopes[0])
        sk2: ScopedKey = n4js.create_network(an, multiple_scopes[1])

        chemicalsystem_sks = n4js.query_chemicalsystems()

        assert len(chemicalsystem_sks) == len(network_tyk2.nodes) * 2
        assert len(n4js.query_chemicalsystems(scope=multiple_scopes[0])) == len(
            network_tyk2.nodes
        )
        assert len(n4js.query_chemicalsystems(name="lig_ejm_31_complex")) == 2
        assert (
            len(
                n4js.query_chemicalsystems(
                    scope=multiple_scopes[0], name="lig_ejm_31_complex"
                )
            )
            == 1
        )

    def test_get_network_transformations(self, n4js, network_tyk2, scope_test):
        an = network_tyk2
        sk: ScopedKey = n4js.create_network(an, scope_test)

        tf_sks = n4js.get_network_transformations(sk)

        assert len(tf_sks) == len(network_tyk2.edges)
        assert set(tf_sk.gufe_key for tf_sk in tf_sks) == set(
            t.key for t in network_tyk2.edges
        )

    def test_get_transformation_networks(self, n4js, network_tyk2, scope_test):
        an = network_tyk2
        sk: ScopedKey = n4js.create_network(an, scope_test)

        tf_sks = n4js.get_network_transformations(sk)
        an_sks = n4js.get_transformation_networks(tf_sks[0])

        assert sk in an_sks
        assert len(an_sks) == 1

    def test_get_network_chemicalsystems(self, n4js, network_tyk2, scope_test):
        an = network_tyk2
        sk: ScopedKey = n4js.create_network(an, scope_test)

        cs_sks = n4js.get_network_chemicalsystems(sk)

        assert len(cs_sks) == len(network_tyk2.nodes)
        assert set(cs_sk.gufe_key for cs_sk in cs_sks) == set(
            cs.key for cs in network_tyk2.nodes
        )

    def test_get_chemicalsystem_networks(self, n4js, network_tyk2, scope_test):
        an = network_tyk2
        sk: ScopedKey = n4js.create_network(an, scope_test)

        cs_sks = n4js.get_network_chemicalsystems(sk)
        an_sks = n4js.get_chemicalsystem_networks(cs_sks[0])

        assert sk in an_sks
        assert len(an_sks) == 1

    def test_get_transformation_chemicalsystems(
        self, n4js, network_tyk2, scope_test, transformation
    ):
        an = network_tyk2
        sk: ScopedKey = n4js.create_network(an, scope_test)

        tf_sk = ScopedKey(gufe_key=transformation.key, **scope_test.dict())

        cs_sks = n4js.get_transformation_chemicalsystems(tf_sk)

        assert len(cs_sks) == 2
        assert set(cs_sk.gufe_key for cs_sk in cs_sks) == set(
            [transformation.stateA.key, transformation.stateB.key]
        )

    def test_get_chemicalsystem_transformations(
        self, n4js, network_tyk2, scope_test, chemicalsystem
    ):
        an = network_tyk2
        sk: ScopedKey = n4js.create_network(an, scope_test)

        cs_sk = ScopedKey(gufe_key=chemicalsystem.key, **scope_test.dict())

        tf_sks = n4js.get_chemicalsystem_transformations(cs_sk)

        tfs = []
        for tf in network_tyk2.edges:
            if chemicalsystem in (tf.stateA, tf.stateB):
                tfs.append(tf)

        assert set(tf_sk.gufe_key for tf_sk in tf_sks) == set(t.key for t in tfs)

    def test_get_transformation_results(
        self,
        n4js: Neo4jStore,
        network_tyk2,
        scope_test,
        transformation,
        protocoldagresults,
    ):
        an = network_tyk2
        network_sk = n4js.create_network(an, scope_test)
        transformation_sk = n4js.get_scoped_key(transformation, scope_test)

        # create a task; pretend we computed it, submit reference for pre-baked
        # result
        task_sk = n4js.create_task(transformation_sk)

        pdr_ref = ProtocolDAGResultRef(
            scope=task_sk.scope,
            obj_key=protocoldagresults[0].key,
            ok=protocoldagresults[0].ok(),
        )

        # push the result
        pdr_ref_sk = n4js.set_task_result(task_sk, pdr_ref)

        # get the result back, at the transformation level
        pdr_ref_sks = n4js.get_transformation_results(transformation_sk)

        assert len(pdr_ref_sks) == 1
        assert pdr_ref_sk in pdr_ref_sks

        # try adding a new task, then adding the same result to it
        # should result in two tasks pointing to the same result, and yield
        # only one
        task_sk2 = n4js.create_task(transformation_sk)
        n4js.set_task_result(task_sk2, pdr_ref)
        pdr_ref_sks_2 = n4js.get_transformation_results(transformation_sk)

        assert len(pdr_ref_sks_2) == 1
        assert pdr_ref_sk in pdr_ref_sks_2

        # try adding additional unique results to one of the tasks
        for pdr in protocoldagresults[1:]:
            pdr_ref_ = ProtocolDAGResultRef(
                scope=task_sk.scope, obj_key=pdr.key, ok=pdr.ok()
            )
            # push the result
            n4js.set_task_result(task_sk, pdr_ref_)

        # now get all results back for this transformation
        pdr_ref_sks_3 = n4js.get_transformation_results(transformation_sk)

        assert len(pdr_ref_sks_3) == 3
        assert set([n4js.get_gufe(p).obj_key for p in pdr_ref_sks_3]) == set(
            [p.key for p in protocoldagresults]
        )

    def test_get_transformation_failures(
        self,
        n4js: Neo4jStore,
        network_tyk2_failure,
        scope_test,
        transformation_failure,
        protocoldagresults_failure,
    ):
        an = network_tyk2_failure
        network_sk = n4js.create_network(an, scope_test)
        transformation_sk = n4js.get_scoped_key(transformation_failure, scope_test)

        # create a task; pretend we computed it, submit reference for pre-baked
        # result
        task_sk = n4js.create_task(transformation_sk)

        pdr_ref = ProtocolDAGResultRef(
            scope=task_sk.scope,
            obj_key=protocoldagresults_failure[0].key,
            ok=protocoldagresults_failure[0].ok(),
        )

        # push the result
        pdr_ref_sk = n4js.set_task_result(task_sk, pdr_ref)

        # try to get the result back, at the transformation level
        pdr_ref_sks = n4js.get_transformation_results(transformation_sk)

        assert len(pdr_ref_sks) == 0

        # try to get failure back
        failure_pdr_ref_sks = n4js.get_transformation_failures(transformation_sk)

        assert len(failure_pdr_ref_sks) == 1
        assert pdr_ref_sk in failure_pdr_ref_sks

        # try adding a new task, then adding the same result to it
        # should result in two tasks pointing to the same result, and yield
        # only one
        task_sk2 = n4js.create_task(transformation_sk)
        n4js.set_task_result(task_sk2, pdr_ref)
        pdr_ref_sks_2 = n4js.get_transformation_failures(transformation_sk)

        assert len(pdr_ref_sks_2) == 1
        assert pdr_ref_sk in pdr_ref_sks_2

        # try adding additional unique results to one of the tasks
        for pdr in protocoldagresults_failure[1:]:
            pdr_ref_ = ProtocolDAGResultRef(
                scope=task_sk.scope, obj_key=pdr.key, ok=pdr.ok()
            )
            # push the result
            n4js.set_task_result(task_sk, pdr_ref_)

        # should still get 0 results back for this transformation
        assert len(n4js.get_transformation_results(transformation_sk)) == 0

        # but should get 3 failures back if we ask for those
        pdr_ref_sks_3 = n4js.get_transformation_failures(transformation_sk)

        assert len(pdr_ref_sks_3) == 3
        assert set([n4js.get_gufe(p).obj_key for p in pdr_ref_sks_3]) == set(
            [p.key for p in protocoldagresults_failure]
        )

    ### compute

    def test_register_computeservice(self, n4js, compute_service_id):
        now = datetime.utcnow()
        registration = ComputeServiceRegistration(
            identifier=compute_service_id, registered=now, heartbeat=now
        )

        compute_service_id_ = n4js.register_computeservice(registration)

        assert compute_service_id == compute_service_id_

        csreg = n4js.graph.run(
            f"""
            match (csreg:ComputeServiceRegistration {{identifier: '{compute_service_id}'}})
            return csreg
            """
        ).to_subgraph()

        assert csreg["identifier"] == compute_service_id

        # we round to integer seconds from epoch to avoid somewhat different
        # floats on either side of comparison even if practically the same
        # straight datetime comparisons would sometimes fail depending on timing
        assert int(csreg["registered"].to_native().timestamp()) == int(now.timestamp())
        assert int(csreg["heartbeat"].to_native().timestamp()) == int(now.timestamp())

    def test_deregister_computeservice(self, n4js, compute_service_id):
        now = datetime.utcnow()
        registration = ComputeServiceRegistration(
            identifier=compute_service_id, registered=now, heartbeat=now
        )

        n4js.register_computeservice(registration)

        # try deregistering
        compute_service_id_ = n4js.deregister_computeservice(compute_service_id)

        assert compute_service_id == compute_service_id_

        csreg = n4js.graph.run(
            f"""
            match (csreg:ComputeServiceRegistration {{identifier: '{compute_service_id}'}})
            return csreg
            """
        ).to_subgraph()

        assert csreg is None

    def test_heartbeat_computeservice(self, n4js, compute_service_id):
        now = datetime.utcnow()
        registration = ComputeServiceRegistration(
            identifier=compute_service_id, registered=now, heartbeat=now
        )

        n4js.register_computeservice(registration)

        # perform a heartbeat
        tomorrow = now + timedelta(days=1)
        n4js.heartbeat_computeservice(compute_service_id, tomorrow)

        csreg = n4js.graph.run(
            f"""
            match (csreg:ComputeServiceRegistration {{identifier: '{compute_service_id}'}})
            return csreg
            """
        ).to_subgraph()

        # we round to integer seconds from epoch to avoid somewhat different
        # floats on either side of comparison even if practically the same
        # straight datetime comparisons would sometimes fail depending on timing
        assert int(csreg["registered"].to_native().timestamp()) == int(now.timestamp())
        assert int(csreg["heartbeat"].to_native().timestamp()) == int(
            tomorrow.timestamp()
        )

    def test_expire_registrations(self, n4js, compute_service_id):
        now = datetime.utcnow()
        yesterday = now - timedelta(days=1)
        an_hour_ago = now - timedelta(hours=1)
        registration = ComputeServiceRegistration(
            identifier=compute_service_id, registered=yesterday, heartbeat=an_hour_ago
        )

        n4js.register_computeservice(registration)

        # expire any compute service that had a heartbeat more than 30 mins ago
        thirty_mins_ago = now - timedelta(minutes=30)

        identities = n4js.expire_registrations(expire_time=thirty_mins_ago)

        csreg = n4js.graph.run(
            f"""
            match (csreg:ComputeServiceRegistration {{identifier: '{compute_service_id}'}})
            return csreg
            """
        ).to_subgraph()

        assert csreg is None
        assert compute_service_id in identities

    def test_create_task(self, n4js, network_tyk2, scope_test):
        # add alchemical network, then try generating task
        an = network_tyk2
        n4js.create_network(an, scope_test)

        transformation = list(an.edges)[0]
        transformation_sk = n4js.get_scoped_key(transformation, scope_test)

        task_sk: ScopedKey = n4js.create_task(transformation_sk)

        m = n4js.graph.run(
            f"""
                match (n:Task {{_gufe_key: '{task_sk.gufe_key}', 
                                             _org: '{task_sk.org}', _campaign: '{task_sk.campaign}', 
                                             _project: '{task_sk.project}'}})-[:PERFORMS]->(m:Transformation)
                return m
                """
        ).to_subgraph()

        assert m["_gufe_key"] == transformation.key

    def test_create_task_extends_invalid_deleted(self, n4js, network_tyk2, scope_test):
        # add alchemical network, then try generating task
        an = network_tyk2
        n4js.create_network(an, scope_test)

        transformation = list(an.edges)[0]
        transformation_sk = n4js.get_scoped_key(transformation, scope_test)

        task_sk_invalid = n4js.create_task(transformation_sk)
        n4js.set_task_invalid([task_sk_invalid])

        task_sk_deleted = n4js.create_task(transformation_sk)
        n4js.set_task_deleted([task_sk_deleted])

        with pytest.raises(ValueError, match="Cannot extend"):
            # try and create a task that extends an invalid task
            _ = n4js.create_task(transformation_sk, extends=task_sk_invalid)

        with pytest.raises(ValueError, match="Cannot extend"):
            # try and create a task that extends a deleted task
            _ = n4js.create_task(transformation_sk, extends=task_sk_deleted)

    def test_query_tasks(self, n4js, network_tyk2, scope_test, multiple_scopes):
        an = network_tyk2
        n4js.create_network(an, scope_test)

        task_sks = n4js.query_tasks()
        assert len(task_sks) == 0

        tf_sks = n4js.query_transformations(scope=scope_test)

        for tf_sk in tf_sks[:10]:
            [n4js.create_task(tf_sk) for i in range(3)]

        task_sks = n4js.query_tasks()
        assert len(task_sks) == 10 * 3

        task_sks = n4js.query_tasks(scope=scope_test)
        assert len(task_sks) == 10 * 3

        task_sks = n4js.query_tasks(scope=multiple_scopes[1])
        assert len(task_sks) == 0

        # check that we can query by status
        task_sks = n4js.query_tasks()
        n4js.set_task_invalid(task_sks[:10])

        task_sks = n4js.query_tasks(status="waiting")
        assert len(task_sks) == 10 * 3 - 10

        task_sks = n4js.query_tasks(status="invalid")
        assert len(task_sks) == 10

        task_sks = n4js.query_tasks(status="complete")
        assert len(task_sks) == 0

    def test_get_network_tasks(self, n4js, network_tyk2, scope_test):
        an = network_tyk2
        n4js.create_network(an, scope_test)

        an_sk = n4js.query_networks(scope=scope_test)[0]
        tf_sks = n4js.get_network_transformations(an_sk)

        task_sks = []
        for tf_sk in tf_sks[:10]:
            task_sks.extend([n4js.create_task(tf_sk) for i in range(3)])

        task_sks_network = n4js.get_network_tasks(an_sk)
        assert set(task_sks_network) == set(task_sks)
        assert len(task_sks_network) == len(task_sks)

        n4js.set_task_invalid(task_sks[:10])

        task_sks = n4js.get_network_tasks(an_sk, status=TaskStatusEnum.waiting)
        assert len(task_sks) == len(task_sks_network) - 10

        task_sks = n4js.get_network_tasks(an_sk, status=TaskStatusEnum.invalid)
        assert len(task_sks) == 10

        task_sks = n4js.get_network_tasks(an_sk, status=TaskStatusEnum.complete)
        assert len(task_sks) == 0

    def test_get_task_networks(self, n4js, network_tyk2, scope_test):
        an = network_tyk2
        n4js.create_network(an, scope_test)
        n4js.create_network(AlchemicalNetwork(edges=list(an.edges)[:-2]), scope_test)

        an_sk = n4js.query_networks(scope=scope_test)[0]
        tf_sks = n4js.get_network_transformations(an_sk)

        task_sks = []
        for tf_sk in tf_sks[:10]:
            task_sks.extend([n4js.create_task(tf_sk) for i in range(3)])

        for task_sk in task_sks:
            an_sks = n4js.get_task_networks(task_sk)
            assert an_sk in an_sks
            for an_sk in an_sks:
                assert task_sk in n4js.get_network_tasks(an_sk)

    def test_get_transformation_tasks(self, n4js, network_tyk2, scope_test):
        an = network_tyk2
        network_sk = n4js.create_network(an, scope_test)

        transformation = list(an.edges)[0]
        transformation_sk = n4js.get_scoped_key(transformation, scope_test)

        # create a tree of tasks for a selected transformation
        task_sks = []
        for i in range(3):
            task_i: ScopedKey = n4js.create_task(transformation_sk)
            task_sks.append(task_i)
            for j in range(3):
                task_j = n4js.create_task(transformation_sk, extends=task_i)
                task_sks.append(task_j)
                for k in range(3):
                    task_k = n4js.create_task(transformation_sk, extends=task_j)
                    task_sks.append(task_k)

        # get all tasks for the transformation
        all_task_sks: List[ScopedKey] = n4js.get_transformation_tasks(transformation_sk)

        f = lambda x, y: x**y + x ** (y - 1) + x ** (y - 2)

        assert len(all_task_sks) == f(3, 3)
        assert set(task_sks) == set(all_task_sks)

        # try getting back only tasks extending from a given one
        subtree = n4js.get_transformation_tasks(transformation_sk, extends=task_sks[0])

        assert len(subtree) == f(3, 2) - 1
        assert set(subtree) == set(task_sks[1:13])

        # try getting tasks back in the "graph" representation instead
        # this is a mapping of each Task to the Task they extend, if applicable
        graph = n4js.get_transformation_tasks(transformation_sk, return_as="graph")

        assert len(graph) == len(task_sks)
        assert set(graph.keys()) == set(task_sks)
        assert all([graph[t] == task_sks[0] for t in task_sks[1:13:4]])

    def test_get_task_transformation(
        self,
        n4js: Neo4jStore,
        network_tyk2,
        scope_test,
        protocoldagresults,
    ):
        # create a network with just the transformation we care about
        transformation = list(network_tyk2.edges)[0]
        network_sk = n4js.create_network(
            AlchemicalNetwork(edges=[transformation]), scope_test
        )

        transformation_sk = n4js.get_scoped_key(transformation, scope_test)

        # create a task; use its scoped key to get its transformation
        # this should be the same one we used to spawn the task
        task_sk = n4js.create_task(transformation_sk)

        # get transformations back as both gufe objects and scoped keys
        tf, _ = n4js.get_task_transformation(task_sk)
        tf_sk, _ = n4js.get_task_transformation(task_sk, return_gufe=False)

        assert tf == transformation
        assert tf_sk == transformation_sk

        # pretend we completed this one, and we have a protocoldagresult for it
        pdr_ref = ProtocolDAGResultRef(
            scope=task_sk.scope, obj_key=protocoldagresults[0].key, ok=True
        )

        # try to push the result
        pdr_ref_sk = n4js.set_task_result(task_sk, pdr_ref)

        # create a task that extends the previous one
        task_sk2 = n4js.create_task(transformation_sk, extends=task_sk)

        # get transformations and protocoldagresultrefs as both gufe objects and scoped keys
        tf, protocoldagresultref = n4js.get_task_transformation(task_sk2)
        tf_sk, protocoldagresultref_sk = n4js.get_task_transformation(
            task_sk2, return_gufe=False
        )

        assert pdr_ref == protocoldagresultref
        assert pdr_ref_sk == protocoldagresultref_sk

        assert tf == transformation
        assert tf_sk == transformation_sk

    def test_set_task_priority(self, n4js, network_tyk2, scope_test):
        an = network_tyk2
        network_sk = n4js.create_network(an, scope_test)
        taskhub_sk = n4js.create_taskhub(network_sk)

        transformation = list(an.edges)[0]
        transformation_sk = n4js.get_scoped_key(transformation, scope_test)

        task_sks = [n4js.create_task(transformation_sk) for i in range(3)]

        base_case = n4js.get_task_priority(task_sks)
        assert [10, 10, 10] == base_case

        n4js.set_task_priority([task_sks[0]], 20)
        single_change = n4js.get_task_priority(task_sks)
        assert [20, 10, 10] == single_change

        n4js.set_task_priority(task_sks, 30)
        change_all = n4js.get_task_priority(task_sks)
        assert [30, 30, 30] == change_all

    def test_set_task_priority_returned_keys(self, n4js, network_tyk2, scope_test):
        an = network_tyk2
        network_sk = n4js.create_network(an, scope_test)
        taskhub_sk = n4js.create_taskhub(network_sk)

        transformation = list(an.edges)[0]
        transformation_sk = n4js.get_scoped_key(transformation, scope_test)

        task_sks = [n4js.create_task(transformation_sk) for i in range(3)]

        updated = n4js.set_task_priority(task_sks, 1)
        assert updated == task_sks

        # "updating" includes setting the priority to itself
        # None is only returned when a task doesn't exist
        # run the above block again to check this
        updated = n4js.set_task_priority(task_sks, 1)
        assert updated == task_sks

    def test_set_task_priority_missing_task(self, n4js, network_tyk2, scope_test):
        an = network_tyk2
        network_sk = n4js.create_network(an, scope_test)
        taskhub_sk = n4js.create_taskhub(network_sk)

        transformation = list(an.edges)[0]
        transformation_sk = n4js.get_scoped_key(transformation, scope_test)

        task_sks = [n4js.create_task(transformation_sk) for i in range(3)]
        task_sks_with_fake = task_sks + [
            ScopedKey.from_str("Task-FAKE-test_org-test_campaign-test_project")
        ]

        updated = n4js.set_task_priority(task_sks_with_fake, 1)
        assert updated == task_sks + [None]

    def test_set_task_priority_out_of_bounds(self, n4js, network_tyk2, scope_test):
        an = network_tyk2
        network_sk = n4js.create_network(an, scope_test)
        taskhub_sk = n4js.create_taskhub(network_sk)

        transformation = list(an.edges)[0]
        transformation_sk = n4js.get_scoped_key(transformation, scope_test)

        task_sks = [n4js.create_task(transformation_sk) for i in range(3)]

        msg = "priority must be between"

        # should raise ValueError when providing list
        # of ScopedKeys
        with pytest.raises(ValueError, match=msg):
            n4js.set_task_priority(task_sks, -1)

        with pytest.raises(ValueError, match=msg):
            n4js.set_task_priority(task_sks, 2**63)

    def test_get_task_priority(self, n4js, network_tyk2, scope_test):
        an = network_tyk2
        network_sk = n4js.create_network(an, scope_test)
        taskhub_sk = n4js.create_taskhub(network_sk)

        transformation = list(an.edges)[0]
        transformation_sk = n4js.get_scoped_key(transformation, scope_test)

        task_sks = [n4js.create_task(transformation_sk) for i in range(3)]

        result = n4js.get_task_priority(task_sks)
        assert result == [10, 10, 10]

    def test_get_task_priority_missing_task(self, n4js, network_tyk2, scope_test):
        an = network_tyk2
        network_sk = n4js.create_network(an, scope_test)
        taskhub_sk = n4js.create_taskhub(network_sk)

        transformation = list(an.edges)[0]
        transformation_sk = n4js.get_scoped_key(transformation, scope_test)

        task_sks = [n4js.create_task(transformation_sk) for i in range(3)]
        task_sks_with_fake = task_sks + [
            ScopedKey.from_str("Task-FAKE-test_org-test_campaign-test_project")
        ]

        result = n4js.get_task_priority(task_sks_with_fake)
        assert result == [10, 10, 10] + [None]

    def test_create_taskhub(self, n4js, network_tyk2, scope_test):
        # add alchemical network, then try adding a taskhub
        an = network_tyk2
        network_sk = n4js.create_network(an, scope_test)

        # create taskhub
        taskhub_sk: ScopedKey = n4js.create_taskhub(network_sk)

        # verify creation looks as we expect
        m = n4js.graph.run(
            f"""
                match (n:TaskHub {{_gufe_key: '{taskhub_sk.gufe_key}', 
                                             _org: '{taskhub_sk.org}', _campaign: '{taskhub_sk.campaign}', 
                                             _project: '{taskhub_sk.project}'}})-[:PERFORMS]->(m:AlchemicalNetwork)
                return m
                """
        ).to_subgraph()

        assert m["_gufe_key"] == an.key

        # try adding the task hub again; this should yield exactly the same node
        taskhub_sk2: ScopedKey = n4js.create_taskhub(network_sk)

        assert taskhub_sk2 == taskhub_sk

        records = n4js.graph.run(
            f"""
                match (n:TaskHub {{network: '{network_sk}', 
                                             _org: '{taskhub_sk.org}', _campaign: '{taskhub_sk.campaign}', 
                                             _project: '{taskhub_sk.project}'}})-[:PERFORMS]->(m:AlchemicalNetwork)
                return n
                """
        )

        assert len(list(records)) == 1

    def test_create_taskhub_weight(self, n4js, network_tyk2, scope_test):
        an = network_tyk2
        network_sk = n4js.create_network(an, scope_test)

        # create taskhub
        taskhub_sk: ScopedKey = n4js.create_taskhub(network_sk)

        n = n4js.graph.run(
            f"""
                match (n:TaskHub)
                return n
                """
        ).to_subgraph()

        assert n["weight"] == 0.5

        # change the weight
        n4js.set_taskhub_weight(network_sk, 0.7)

        n = n4js.graph.run(
            f"""
                match (n:TaskHub)
                return n
                """
        ).to_subgraph()

        assert n["weight"] == 0.7

    def test_query_taskhubs(self, n4js: Neo4jStore, network_tyk2, scope_test):
        an = network_tyk2
        network_sk = n4js.create_network(an, scope_test)
        taskhub_sk: ScopedKey = n4js.create_taskhub(network_sk)

        # add a slightly different network
        an2 = AlchemicalNetwork(
            edges=list(an.edges)[:-1], name="tyk2_relative_benchmark_-1"
        )
        network_sk2 = n4js.create_network(an2, scope_test)
        taskhub_sk2: ScopedKey = n4js.create_taskhub(network_sk2)

        tq_sks: List[ScopedKey] = n4js.query_taskhubs()
        assert len(tq_sks) == 2
        assert all([isinstance(i, ScopedKey) for i in tq_sks])

        tq_dict: Dict[ScopedKey, TaskHub] = n4js.query_taskhubs(return_gufe=True)
        assert len(tq_dict) == 2
        assert all([isinstance(i, TaskHub) for i in tq_dict.values()])

    def test_get_taskhub_actioned_tasks(
        self, n4js: Neo4jStore, network_tyk2, scope_test
    ):
        an = network_tyk2
        network_sk = n4js.create_network(an, scope_test)
        taskhub_sk: ScopedKey = n4js.create_taskhub(network_sk)
        transformation = list(an.edges)[0]
        transformation_sk = n4js.get_scoped_key(transformation, scope_test)

        task_sks = [n4js.create_task(transformation_sk) for i in range(5)]

        # do not action the tasks yet; should get back nothing
        actioned_tasks = n4js.get_taskhub_actioned_tasks(taskhub_sk)
        assert actioned_tasks == {}

        # action 3 of 5 tasks
        n4js.action_tasks(task_sks[:3], taskhub_sk)

        actioned_tasks = n4js.get_taskhub_actioned_tasks(taskhub_sk)

        assert len(actioned_tasks) == 3
        assert all([task_i in task_sks for task_i in actioned_tasks])

        # check that we get back expected weights
        all([w == 0.5 for w in actioned_tasks.values()])

    def test_get_task_actioned_networks(
        self, n4js: Neo4jStore, network_tyk2, scope_test
    ):
        an_1 = network_tyk2
        an_2 = network_tyk2.copy_with_replacements(name=an_1.name + "_2")

        network_sk_1 = n4js.create_network(an_1, scope_test)
        network_sk_2 = n4js.create_network(an_2, scope_test)

        taskhub_sk_1 = n4js.create_taskhub(network_sk_1)
        taskhub_sk_2 = n4js.create_taskhub(network_sk_2)

        transformation = list(an_1.edges)[0]
        transformation_sk = n4js.get_scoped_key(transformation, scope_test)

        task_sk = n4js.create_task(transformation_sk)

        # do not action the task yet; should get back nothing
        an_sks = n4js.get_task_actioned_networks(task_sk)
        assert an_sks == {}

        n4js.action_tasks([task_sk], taskhub_sk_1)
        n4js.action_tasks([task_sk], taskhub_sk_2)

        an_sks = n4js.get_task_actioned_networks(task_sk)

        assert all([an_sk in an_sks for an_sk in [network_sk_1, network_sk_2]])

        # check that we get back expected weights
        all([w == 0.5 for w in an_sks.values()])

    def test_get_taskhub_weight(self, n4js: Neo4jStore, network_tyk2, scope_test):
        network_sk = n4js.create_network(network_tyk2, scope_test)
        n4js.create_taskhub(network_sk)

        q = f"""
        MATCH (network:AlchemicalNetwork {{_scoped_key: '{network_sk}'}})--(taskhub:TaskHub)
        return taskhub.weight
        """

        weight = n4js.graph.evaluate(q)
        weight_ = n4js.get_taskhub_weight(network_sk)

        assert weight == 0.5
        assert weight_ == 0.5

    def test_set_taskhub_weight(self, n4js: Neo4jStore, network_tyk2, scope_test):
        network_sk = n4js.create_network(network_tyk2, scope_test)
        n4js.create_taskhub(network_sk)

        n4js.set_taskhub_weight(network_sk, 1.0)
        weight = n4js.get_taskhub_weight(network_sk)

        assert weight == 1.0

    def test_action_task(self, n4js: Neo4jStore, network_tyk2, scope_test):
        an = network_tyk2
        network_sk = n4js.create_network(an, scope_test)
        taskhub_sk: ScopedKey = n4js.create_taskhub(network_sk)

        transformation = list(an.edges)[0]
        transformation_sk = n4js.get_scoped_key(transformation, scope_test)

        # create 10 tasks
        task_sks = [n4js.create_task(transformation_sk) for i in range(10)]

        # action the tasks
        n4js.action_tasks(task_sks, taskhub_sk)

        # count tasks actioned
        actioned_task_sks = n4js.get_taskhub_tasks(taskhub_sk)
        assert set(task_sks) == set(actioned_task_sks)
        assert len(task_sks) == 10

        # add a second network, with the transformation above missing
        # try to add a task from that transformation to the new network's hub
        # this should fail
        an2 = AlchemicalNetwork(
            edges=list(an.edges)[1:], name="tyk2_relative_benchmark_-1"
        )
        assert transformation not in an2.edges

        network_sk2 = n4js.create_network(an2, scope_test)
        taskhub_sk2: ScopedKey = n4js.create_taskhub(network_sk2)

        task_sks_fail = n4js.action_tasks(task_sks, taskhub_sk2)
        assert all([i is None for i in task_sks_fail])

    def test_action_task_other_statuses(
        self, n4js: Neo4jStore, network_tyk2, scope_test
    ):
        an = network_tyk2
        network_sk = n4js.create_network(an, scope_test)
        taskhub_sk: ScopedKey = n4js.create_taskhub(network_sk)

        transformation = list(an.edges)[0]
        transformation_sk = n4js.get_scoped_key(transformation, scope_test)

        # create 10 tasks
        task_sks = [n4js.create_task(transformation_sk) for i in range(6)]

        # set all but first task to running
        n4js.set_task_running(task_sks[1:])

        # set 1 task for each available status
        n4js.set_task_error(task_sks[2:3])
        n4js.set_task_complete(task_sks[3:4])
        n4js.set_task_invalid(task_sks[4:5])
        n4js.set_task_deleted(task_sks[5:6])

        # action all tasks; only those that are 'waiting', 'running', or
        # 'error' should be actioned
        actioned = n4js.action_tasks(task_sks, taskhub_sk)

        assert actioned[:3] == task_sks[:3]
        assert actioned[3:] == [None] * 3

    def test_action_task_extends(self, n4js: Neo4jStore, network_tyk2, scope_test):
        an = network_tyk2
        network_sk = n4js.create_network(an, scope_test)
        taskhub_sk: ScopedKey = n4js.create_taskhub(network_sk)

        transformation = list(an.edges)[0]
        transformation_sk = n4js.get_scoped_key(transformation, scope_test)

        # create 10 tasks that extend in an EXTENDS chain
        first_task = n4js.create_task(transformation_sk)
        collected_sks = [first_task]
        prev = first_task
        for i in range(9):
            curr = n4js.create_task(transformation_sk, extends=prev)
            collected_sks.append(curr)
            prev = curr

        # action the tasks
        actioned_task_sks = n4js.action_tasks(collected_sks, taskhub_sk)
        assert set(actioned_task_sks) == set(collected_sks)

    def test_get_unclaimed_tasks(
        self, n4js: Neo4jStore, network_tyk2, scope_test, compute_service_id
    ):
        an = network_tyk2
        network_sk = n4js.create_network(an, scope_test)
        taskhub_sk: ScopedKey = n4js.create_taskhub(network_sk)

        n4js.register_computeservice(
            ComputeServiceRegistration.from_now(compute_service_id)
        )

        transformation = list(an.edges)[0]
        transformation_sk = n4js.get_scoped_key(transformation, scope_test)

        # create 10 tasks
        task_sks = [n4js.create_task(transformation_sk) for i in range(10)]

        # action the tasks
        n4js.action_tasks(task_sks, taskhub_sk)

        # claim a single task; There is no deterministic ordering of tasks, so
        # simply test that the claimed task is one of the actioned tasks
        claimed = n4js.claim_taskhub_tasks(taskhub_sk, compute_service_id)

        assert claimed[0] in task_sks

        # query for unclaimed tasks
        unclaimed = n4js.get_taskhub_unclaimed_tasks(taskhub_sk)

        assert set(unclaimed) == set(task_sks) - set(claimed)
        assert len(unclaimed) == 9

    def test_get_set_weights(self, n4js: Neo4jStore, network_tyk2, scope_test):
        an = network_tyk2
        network_sk = n4js.create_network(an, scope_test)
        taskhub_sk: ScopedKey = n4js.create_taskhub(network_sk)

        transformation = list(an.edges)[0]
        transformation_sk = n4js.get_scoped_key(transformation, scope_test)

        # create 10 tasks
        task_sks = [n4js.create_task(transformation_sk) for i in range(10)]
        n4js.action_tasks(task_sks, taskhub_sk)

        # weights should all be the default 0.5
        weights = n4js.get_task_weights(task_sks, taskhub_sk)
        assert all([w == 0.5 for w in weights])

        # set weights on the tasks to be all 1.0
        n4js.set_task_weights(task_sks, taskhub_sk, weight=1.0)
        weights = n4js.get_task_weights(task_sks, taskhub_sk)
        assert all([w == 1.0 for w in weights])

    def test_cancel_task(self, n4js, network_tyk2, scope_test):
        an = network_tyk2
        network_sk = n4js.create_network(an, scope_test)
        taskhub_sk: ScopedKey = n4js.create_taskhub(network_sk)

        transformation = list(an.edges)[0]
        transformation_sk = n4js.get_scoped_key(transformation, scope_test)

        # create 10 tasks
        task_sks = [n4js.create_task(transformation_sk) for i in range(10)]

        # action the tasks
        actioned = n4js.action_tasks(task_sks, taskhub_sk)

        # cancel the second and third task we created
        canceled = n4js.cancel_tasks(task_sks[1:3], taskhub_sk)

        # check that the hub has the contents we expect
        tasks = n4js.graph.run(
            f"""
                MATCH (tq:TaskHub {{_scoped_key: '{taskhub_sk}'}})-[:ACTIONS]->(task:Task)
                return task
                """
        )
        tasks = [record["task"] for record in tasks]

        assert len(tasks) == 8
        assert set([ScopedKey.from_str(t["_scoped_key"]) for t in tasks]) == set(
            actioned
        ) - set(canceled)

    def test_get_taskhub_tasks(self, n4js, network_tyk2, scope_test):
        an = network_tyk2
        network_sk = n4js.create_network(an, scope_test)
        taskhub_sk: ScopedKey = n4js.create_taskhub(network_sk)

        transformation = list(an.edges)[0]
        transformation_sk = n4js.get_scoped_key(transformation, scope_test)

        # create 10 tasks
        task_sks = [n4js.create_task(transformation_sk) for i in range(10)]

        # action the tasks
        actioned = n4js.action_tasks(task_sks, taskhub_sk)
        assert len(actioned) == 10

        # get the full hub back; no particular order
        task_sks = n4js.get_taskhub_tasks(taskhub_sk)

        # no particular order so must check that the sets are equal
        assert set(actioned) == set(task_sks)

        # try getting back as gufe objects instead
        tasks = n4js.get_taskhub_tasks(taskhub_sk, return_gufe=True)

        assert all([t.key == tsk.gufe_key for t, tsk in zip(tasks.values(), task_sks)])

    def test_claim_taskhub_tasks(self, n4js: Neo4jStore, network_tyk2, scope_test):
        an = network_tyk2
        network_sk = n4js.create_network(an, scope_test)
        taskhub_sk: ScopedKey = n4js.create_taskhub(network_sk)

        transformation = list(an.edges)[0]
        transformation_sk = n4js.get_scoped_key(transformation, scope_test)

        # create 10 tasks
        task_sks = [n4js.create_task(transformation_sk) for i in range(10)]

        # shuffle the tasks; want to check that order of claiming is unrelated
        # to order created
        random.shuffle(task_sks)

        # try to claim from an empty hub
        csid = ComputeServiceID("early bird task handler")
        n4js.register_computeservice(ComputeServiceRegistration.from_now(csid))
        nothing = n4js.claim_taskhub_tasks(taskhub_sk, csid)

        assert nothing[0] is None

        # action the tasks
        n4js.action_tasks(task_sks, taskhub_sk)

        # claim a single task; there is no deterministic ordering of tasks, so
        # simply test that the claimed task is one of the actioned tasks
        csid = ComputeServiceID("the best task handler")
        n4js.register_computeservice(ComputeServiceRegistration.from_now(csid))
        claimed = n4js.claim_taskhub_tasks(taskhub_sk, csid)

        assert claimed[0] in task_sks

        # filter out the claimed task so that we have clean list of remaining
        # tasks
        remaining_tasks = n4js.get_taskhub_unclaimed_tasks(taskhub_sk)

        # set all tasks to priority 5, first task to priority 1; claim should
        # yield first task
        n4js.set_task_priority(remaining_tasks, 5)
        n4js.set_task_priority([remaining_tasks[0]], 1)

        csid = ComputeServiceID("another task handler")
        n4js.register_computeservice(ComputeServiceRegistration.from_now(csid))
        claimed2 = n4js.claim_taskhub_tasks(taskhub_sk, csid)
        assert claimed2[0] == remaining_tasks[0]

        remaining_tasks = n4js.get_taskhub_unclaimed_tasks(taskhub_sk)

        # next task claimed should be one of the remaining tasks
        csid = ComputeServiceID("yet another task handler")
        n4js.register_computeservice(ComputeServiceRegistration.from_now(csid))
        claimed3 = n4js.claim_taskhub_tasks(taskhub_sk, csid)
        assert claimed3[0] in remaining_tasks

        remaining_tasks = n4js.get_taskhub_unclaimed_tasks(taskhub_sk)

        # try to claim multiple tasks
        csid = ComputeServiceID("last task handler")
        n4js.register_computeservice(ComputeServiceRegistration.from_now(csid))
        claimed4 = n4js.claim_taskhub_tasks(taskhub_sk, csid, count=4)
        assert len(claimed4) == 4
        for sk in claimed4:
            assert sk in remaining_tasks

        # exhaust the hub
        claimed5 = n4js.claim_taskhub_tasks(taskhub_sk, csid, count=3)

        # try to claim from a hub with no tasks available
        claimed6 = n4js.claim_taskhub_tasks(taskhub_sk, csid, count=2)
        assert claimed6 == [None] * 2

    def test_action_claim_task_extends(
        self, n4js: Neo4jStore, network_tyk2, scope_test
    ):
        # tests the ability to action and claim a set of tasks in an
        # EXTENDS chain
        an = network_tyk2
        network_sk = n4js.create_network(an, scope_test)
        taskhub_sk: ScopedKey = n4js.create_taskhub(network_sk)

        transformation = list(an.edges)[0]
        transformation_sk = n4js.get_scoped_key(transformation, scope_test)

        # create 10 tasks that extend in an EXTENDS chain
        first_task = n4js.create_task(transformation_sk)
        collected_sks = [first_task]
        prev = first_task
        for i in range(9):
            curr = n4js.create_task(transformation_sk, extends=prev)
            collected_sks.append(curr)
            prev = curr

        # action the tasks
        actioned_task_sks = n4js.action_tasks(collected_sks, taskhub_sk)
        assert set(actioned_task_sks) == set(collected_sks)

        csid = ComputeServiceID("task handler")
        n4js.register_computeservice(ComputeServiceRegistration.from_now(csid))

        # claim the first task
        claimed_task_sks = n4js.claim_taskhub_tasks(taskhub_sk, csid)

        assert claimed_task_sks == collected_sks[:1]

        # claim the next 9 tasks
        claimed_task_sks = n4js.claim_taskhub_tasks(taskhub_sk, csid, count=9)
        # oops the extends task is still running!
        assert claimed_task_sks == [None] * 9

        # complete the extends task
        n4js.set_task_complete([first_task])

        # claim the next task again
        claimed_task_sks = n4js.claim_taskhub_tasks(taskhub_sk, csid, count=1)
        assert claimed_task_sks == collected_sks[1:2]

    def test_action_claim_task_extends_non_extends(
        self, n4js: Neo4jStore, network_tyk2, scope_test
    ):
        # tests the ability to action and claim a set of tasks that have a mix of
        # EXTENDS and non-EXTENDS tasks
        an = network_tyk2
        network_sk = n4js.create_network(an, scope_test)
        taskhub_sk: ScopedKey = n4js.create_taskhub(network_sk)

        transformation = list(an.edges)[0]
        transformation_sk = n4js.get_scoped_key(transformation, scope_test)

        # create 10 tasks that extend in an EXTENDS chain
        first_task = n4js.create_task(transformation_sk)
        collected_sks = [first_task]
        prev = first_task
        for i in range(9):
            curr = n4js.create_task(transformation_sk, extends=prev)
            collected_sks.append(curr)
            prev = curr

        # create another two tasks that don't extend anything
        extra_task_1 = n4js.create_task(transformation_sk)
        extra_task_2 = n4js.create_task(transformation_sk)
        extra_tasks = [extra_task_1, extra_task_2]
        collected_sks.extend(extra_tasks)

        # action the tasks
        actioned_task_sks = n4js.action_tasks(collected_sks, taskhub_sk)
        assert set(actioned_task_sks) == set(collected_sks)

        csid = ComputeServiceID("task handler")
        n4js.register_computeservice(ComputeServiceRegistration.from_now(csid))

        # claim the first task **3** tasks, this set should be the first extends
        # task and the two non-extends tasks
        claimed_task_sks = n4js.claim_taskhub_tasks(taskhub_sk, csid, count=3)

        assert set(claimed_task_sks) == set([first_task] + extra_tasks)

        # claim the next 10 tasks
        claimed_task_sks = n4js.claim_taskhub_tasks(taskhub_sk, csid, count=10)
        # oops the extends task is still running and there should be no other tasks to grab
        assert claimed_task_sks == [None] * 10

        # complete the extends task
        n4js.set_task_complete([first_task])

        # claim the next task again
        claimed_task_sks = n4js.claim_taskhub_tasks(taskhub_sk, csid, count=1)
        assert claimed_task_sks == collected_sks[1:2]

    def test_action_claim_task_extends_bifuricating(
        self, n4js: Neo4jStore, network_tyk2, scope_test
    ):
        # tests the ability to action and claim a set of tasks in an
        # EXTENDS chain
        an = network_tyk2
        network_sk = n4js.create_network(an, scope_test)
        taskhub_sk: ScopedKey = n4js.create_taskhub(network_sk)

        transformation = list(an.edges)[0]
        transformation_sk = n4js.get_scoped_key(transformation, scope_test)

        # create 7 tasks that extend in a bifuricating  EXTENDS chain

        first_task = n4js.create_task(transformation_sk)

        layer_two_1 = n4js.create_task(transformation_sk, extends=first_task)
        layer_two_2 = n4js.create_task(transformation_sk, extends=first_task)

        layer_three_1 = n4js.create_task(transformation_sk, extends=layer_two_1)
        layer_three_2 = n4js.create_task(transformation_sk, extends=layer_two_1)
        layer_three_3 = n4js.create_task(transformation_sk, extends=layer_two_2)
        layer_three_4 = n4js.create_task(transformation_sk, extends=layer_two_2)

        collected_sks = [
            first_task,
            layer_two_1,
            layer_two_2,
            layer_three_1,
            layer_three_2,
            layer_three_3,
            layer_three_4,
        ]
        # action the tasks
        actioned_task_sks = n4js.action_tasks(collected_sks, taskhub_sk)
        assert set(actioned_task_sks) == set(collected_sks)

        csid = ComputeServiceID("task handler")
        n4js.register_computeservice(ComputeServiceRegistration.from_now(csid))

        # claim the first task
        claimed_task_sks = n4js.claim_taskhub_tasks(taskhub_sk, csid)

        assert claimed_task_sks == [first_task]
        # complete the first task
        n4js.set_task_complete([first_task])

        # claim the next layer of tasks, should be all of layer two
        claimed_task_sks = n4js.claim_taskhub_tasks(taskhub_sk, csid, count=2)
        assert set(claimed_task_sks) == set([layer_two_1, layer_two_2])

        # complete the layer two tasks
        n4js.set_task_complete([layer_two_1, layer_two_2])

        # claim the next layer of tasks, should be all of layer three
        claimed_task_sks = n4js.claim_taskhub_tasks(taskhub_sk, csid, count=4)
        assert set(claimed_task_sks) == set(
            [layer_three_1, layer_three_2, layer_three_3, layer_three_4]
        )

    def test_claim_task_byweight(self, n4js: Neo4jStore, network_tyk2, scope_test):
        an = network_tyk2
        network_sk = n4js.create_network(an, scope_test)
        taskhub_sk: ScopedKey = n4js.create_taskhub(network_sk)

        transformation = list(an.edges)[0]
        transformation_sk = n4js.get_scoped_key(transformation, scope_test)

        # create 10 tasks
        task_sks = [n4js.create_task(transformation_sk) for i in range(10)]

        # action the tasks
        n4js.action_tasks(task_sks, taskhub_sk)

        # shuffle the tasks; want to check that order of claiming is unrelated
        # to order actioned
        random.shuffle(task_sks)

        # set weights on the tasks to be all 0, disabling them
        n4js.set_task_weights(task_sks, taskhub_sk, weight=0)

        # set the weight of the first task to be 1
        weight_dict = {task_sks[0]: 1.0}
        n4js.set_task_weights(weight_dict, taskhub_sk)

        csid = ComputeServiceID("the best task handler")
        n4js.register_computeservice(ComputeServiceRegistration.from_now(csid))

        # check that the claimed task is the first task
        claimed = n4js.claim_taskhub_tasks(taskhub_sk, csid)
        assert claimed[0] == task_sks[0]

        # claim again; should get None as no other tasks have any weight
        claimed_again = n4js.claim_taskhub_tasks(taskhub_sk, csid)
        assert claimed_again[0] == None

    def test_get_scope_status(self, n4js: Neo4jStore, network_tyk2, scope_test):
        an = network_tyk2
        an_sk = n4js.create_network(an, scope_test)

        tf_sks = n4js.get_network_transformations(an_sk)

        task_sks = []
        for tf_sk in tf_sks:
            task_sks.append(n4js.create_task(tf_sk))

        # try all scopes first
        status = n4js.get_scope_status(Scope())
        assert len(status) == 1
        assert len(task_sks) == status["waiting"]

        # try specific scope
        status = n4js.get_scope_status(scope_test)
        assert len(status) == 1
        assert len(task_sks) == status["waiting"]

        # try a different scope
        status = n4js.get_scope_status(Scope(org="test_org_1"))
        assert status == {}

        # change some task statuses
        n4js.set_task_invalid(task_sks[:10])

        # try specific scope
        status = n4js.get_scope_status(scope_test)
        assert len(status) == 2
        assert status["waiting"] == len(task_sks) - 10
        assert status["invalid"] == 10

    def test_get_network_status(self, n4js: Neo4jStore, network_tyk2, scope_test):
        an = network_tyk2
        an_sk = n4js.create_network(an, scope_test)

        tf_sks = n4js.get_network_transformations(an_sk)

        task_sks = []
        for tf_sk in tf_sks:
            task_sks.append(n4js.create_task(tf_sk))

        status = n4js.get_network_status(an_sk)
        assert len(status) == 1
        assert status["waiting"] == len(task_sks)

        # change some task statuses
        n4js.set_task_invalid(task_sks[:10])

        status = n4js.get_network_status(an_sk)
        assert len(status) == 2
        assert status["waiting"] == len(task_sks) - 10
        assert status["invalid"] == 10

    def test_get_transformation_status(
        self, n4js: Neo4jStore, network_tyk2, scope_test
    ):
        an = network_tyk2
        an_sk = n4js.create_network(an, scope_test)

        tf_sks = n4js.get_network_transformations(an_sk)[:3]

        task_sks = []
        for tf_sk in tf_sks:
            task_sks.append([n4js.create_task(tf_sk) for i in range(3)])

            status = n4js.get_transformation_status(tf_sk)
            assert status == {"waiting": 3}

        for tf_task_sks in task_sks:
            # change some task statuses
            n4js.set_task_invalid(tf_task_sks[:1])

        for tf_sk in tf_sks:
            status = n4js.get_transformation_status(tf_sk)
            assert status == {"waiting": 2, "invalid": 1}

    def test_set_task_result(self, n4js: Neo4jStore, network_tyk2, scope_test, tmpdir):
        an = network_tyk2
        network_sk = n4js.create_network(an, scope_test)
        taskhub_sk: ScopedKey = n4js.create_taskhub(network_sk)

        transformation = list(an.edges)[0]
        transformation_sk = n4js.get_scoped_key(transformation, scope_test)

        # create a task; compute its result, and attempt to submit it
        task_sk = n4js.create_task(transformation_sk)

        transformation, protocoldag_prev = n4js.get_task_transformation(task_sk)
        protocoldag = transformation.create(
            extends=protocoldag_prev,
            name=str(task_sk),
        )

        # execute the task
        with tmpdir.as_cwd():
            shared_basedir = Path("shared").absolute()
            shared_basedir.mkdir()
            scratch_basedir = Path("scratch").absolute()
            scratch_basedir.mkdir()

            protocoldagresult = execute_DAG(
                protocoldag,
                shared_basedir=shared_basedir,
                scratch_basedir=scratch_basedir,
            )

        pdr_ref = ProtocolDAGResultRef(
            scope=task_sk.scope, obj_key=protocoldagresult.key, ok=True
        )

        # try to push the result
        n4js.set_task_result(task_sk, pdr_ref)

        n = n4js.graph.run(
            f"""
                match (n:ProtocolDAGResultRef)<-[:RESULTS_IN]-(t:Task)
                return n
                """
        ).to_subgraph()

        assert n["location"] == pdr_ref.location
        assert n["obj_key"] == str(protocoldagresult.key)

    def test_get_task_results(
        self,
        n4js: Neo4jStore,
        network_tyk2,
        scope_test,
        transformation,
        protocoldagresults,
    ):
        an = network_tyk2
        network_sk = n4js.create_network(an, scope_test)
        transformation_sk = n4js.get_scoped_key(transformation, scope_test)

        # create a task; pretend we computed it, submit reference for pre-baked
        # result
        task_sk = n4js.create_task(transformation_sk)

        pdr_ref = ProtocolDAGResultRef(
            scope=task_sk.scope,
            obj_key=protocoldagresults[0].key,
            ok=protocoldagresults[0].ok(),
        )

        # push the result
        pdr_ref_sk = n4js.set_task_result(task_sk, pdr_ref)

        # get the result back
        pdr_ref_sks = n4js.get_task_results(task_sk)

        assert len(pdr_ref_sks) == 1
        assert pdr_ref_sk in pdr_ref_sks

        # try doing it again; should be idempotent
        n4js.set_task_result(task_sk, pdr_ref)
        pdr_ref_sks = n4js.get_task_results(task_sk)

        assert len(pdr_ref_sks) == 1
        assert pdr_ref_sk in pdr_ref_sks

        # if we add a different result, should now have 2
        pdr_ref2 = ProtocolDAGResultRef(
            scope=task_sk.scope,
            obj_key=protocoldagresults[1].key,
            ok=protocoldagresults[1].ok(),
        )

        # push the result
        pdr_ref2_sk = n4js.set_task_result(task_sk, pdr_ref2)

        # get the result back
        pdr_ref_sks = n4js.get_task_results(task_sk)

        assert len(pdr_ref_sks) == 2
        assert pdr_ref_sk in pdr_ref_sks
        assert pdr_ref2_sk in pdr_ref_sks

    def test_get_task_failures(
        self,
        n4js: Neo4jStore,
        network_tyk2_failure,
        scope_test,
        transformation_failure,
        protocoldagresults_failure,
    ):
        an = network_tyk2_failure
        network_sk = n4js.create_network(an, scope_test)
        transformation_sk = n4js.get_scoped_key(transformation_failure, scope_test)

        # create a task; pretend we computed it, submit reference for pre-baked
        # result
        task_sk = n4js.create_task(transformation_sk)

        pdr_ref = ProtocolDAGResultRef(
            scope=task_sk.scope,
            obj_key=protocoldagresults_failure[0].key,
            ok=protocoldagresults_failure[0].ok(),
        )

        # push the result
        pdr_ref_sk = n4js.set_task_result(task_sk, pdr_ref)

        # try get results back
        pdr_ref_sks = n4js.get_task_results(task_sk)

        assert len(pdr_ref_sks) == 0
        assert pdr_ref_sk not in pdr_ref_sks

        # try to get failure back
        failure_pdr_ref_sks = n4js.get_task_failures(task_sk)

        assert len(failure_pdr_ref_sks) == 1
        assert pdr_ref_sk in failure_pdr_ref_sks

        # try doing it again; should be idempotent
        n4js.set_task_result(task_sk, pdr_ref)
        failure_pdr_ref_sks = n4js.get_task_failures(task_sk)

        assert len(failure_pdr_ref_sks) == 1
        assert pdr_ref_sk in failure_pdr_ref_sks

        # if we add a different failure, should now have 2
        pdr_ref2 = ProtocolDAGResultRef(
            scope=task_sk.scope,
            obj_key=protocoldagresults_failure[1].key,
            ok=protocoldagresults_failure[1].ok(),
        )

        # push the result
        pdr_ref2_sk = n4js.set_task_result(task_sk, pdr_ref2)

        # get the result back
        failure_pdr_ref_sks = n4js.get_task_failures(task_sk)

        assert len(failure_pdr_ref_sks) == 2
        assert pdr_ref_sk in failure_pdr_ref_sks
        assert pdr_ref2_sk in failure_pdr_ref_sks

    ### authentication

    @pytest.mark.parametrize(
        "credential_type", [CredentialedUserIdentity, CredentialedComputeIdentity]
    )
    def test_create_credentialed_entity(
        self, n4js: Neo4jStore, credential_type: CredentialedEntity
    ):
        user = credential_type(
            identifier="bill",
            hashed_key=hash_key("and ted"),
        )

        cls_name = credential_type.__name__

        n4js.create_credentialed_entity(user)

        n = n4js.graph.run(
            f"""
            match (n:{cls_name} {{identifier: '{user.identifier}'}})
            return n
            """
        ).to_subgraph()

        assert n["identifier"] == user.identifier
        assert n["hashed_key"] == user.hashed_key

    @pytest.mark.parametrize(
        "credential_type", [CredentialedUserIdentity, CredentialedComputeIdentity]
    )
    def test_get_credentialed_entity(
        self, n4js: Neo4jStore, credential_type: CredentialedEntity
    ):
        user = credential_type(
            identifier="bill",
            hashed_key=hash_key("and ted"),
        )

        n4js.create_credentialed_entity(user)

        # get the user back
        user_g = n4js.get_credentialed_entity(user.identifier, credential_type)

        assert user_g == user

    @pytest.mark.parametrize(
        "credential_type", [CredentialedUserIdentity, CredentialedComputeIdentity]
    )
    def test_list_credentialed_entities(
        self, n4js: Neo4jStore, credential_type: CredentialedEntity
    ):
        identities = ("bill", "ted", "napoleon")

        for ident in identities:
            user = credential_type(
                identifier=ident,
                hashed_key=hash_key("a string for a key"),
            )

            n4js.create_credentialed_entity(user)

        # get the user back
        identities_ = n4js.list_credentialed_entities(credential_type)

        assert set(identities) == set(identities_)

    @pytest.mark.parametrize(
        "credential_type", [CredentialedUserIdentity, CredentialedComputeIdentity]
    )
    def test_remove_credentialed_entity(
        self, n4js: Neo4jStore, credential_type: CredentialedEntity
    ):
        user = credential_type(
            identifier="bill",
            hashed_key=hash_key("and ted"),
        )

        n4js.create_credentialed_entity(user)

        # get the user back
        user_g = n4js.get_credentialed_entity(user.identifier, credential_type)

        assert user_g == user

        n4js.remove_credentialed_identity(user.identifier, credential_type)
        with pytest.raises(KeyError):
            n4js.get_credentialed_entity(user.identifier, credential_type)

    @pytest.mark.parametrize(
        "credential_type", [CredentialedUserIdentity, CredentialedComputeIdentity]
    )
    @pytest.mark.parametrize(
        "scope_strs", (["*-*-*"], ["a-*-*"], ["a-b-*"], ["a-b-c", "a-b-d"])
    )
    def test_list_scope(
        self,
        n4js: Neo4jStore,
        credential_type: CredentialedEntity,
        scope_strs: List[str],
    ):
        user = credential_type(
            identifier="bill",
            hashed_key=hash_key("and ted"),
        )

        n4js.create_credentialed_entity(user)
        ref_scopes = []
        for scope_str in scope_strs:
            scope = Scope.from_str(scope_str)
            ref_scopes.append(scope)
            n4js.add_scope(user.identifier, credential_type, scope)

        scopes = n4js.list_scopes(user.identifier, credential_type)
        assert set(scopes) == set(ref_scopes)

    @pytest.mark.parametrize(
        "credential_type", [CredentialedUserIdentity, CredentialedComputeIdentity]
    )
    @pytest.mark.parametrize("scope_str", ("*-*-*", "a-*-*", "a-b-*", "a-b-c"))
    def test_add_scope(
        self, n4js: Neo4jStore, credential_type: CredentialedEntity, scope_str: str
    ):
        user = credential_type(
            identifier="bill",
            hashed_key=hash_key("and ted"),
        )

        n4js.create_credentialed_entity(user)

        scope = Scope.from_str(scope_str)

        n4js.add_scope(user.identifier, credential_type, scope)

        q = f"""
        MATCH (n:{credential_type.__name__} {{identifier: '{user.identifier}'}})
        RETURN n
        """
        scopes_qr = n4js.graph.run(q).to_subgraph()
        scopes = scopes_qr.get("scopes")
        assert len(scopes) == 1

        new_scope = Scope.from_str(scopes[0])
        assert new_scope == scope

    @pytest.mark.parametrize(
        "credential_type", [CredentialedUserIdentity, CredentialedComputeIdentity]
    )
    def test_add_scope_duplicate(
        self, n4js: Neo4jStore, credential_type: CredentialedEntity
    ):
        user = credential_type(
            identifier="bill",
            hashed_key=hash_key("and ted"),
        )

        n4js.create_credentialed_entity(user)

        scope1 = Scope.from_str("*-*-*")
        scope2 = Scope.from_str("*-*-*")

        n4js.add_scope(user.identifier, credential_type, scope1)
        n4js.add_scope(user.identifier, credential_type, scope2)

        q = f"""
        MATCH (n:{credential_type.__name__} {{identifier: '{user.identifier}'}})
        RETURN n
        """
        scopes_qr = n4js.graph.run(q).to_subgraph()
        scopes = scopes_qr.get("scopes")
        assert len(scopes) == 1

        new_scope = Scope.from_str(scopes[0])
        assert new_scope == scope1

    @pytest.mark.parametrize(
        "credential_type", [CredentialedUserIdentity, CredentialedComputeIdentity]
    )
    @pytest.mark.parametrize("scope_str", ("*-*-*", "a-*-*", "a-b-*", "a-b-c"))
    def test_remove_scope(
        self, n4js: Neo4jStore, credential_type: CredentialedEntity, scope_str: str
    ):
        user = credential_type(
            identifier="bill",
            hashed_key=hash_key("and ted"),
        )

        n4js.create_credentialed_entity(user)

        scope = Scope.from_str(scope_str)
        not_removed = Scope.from_str("scope-not-removed")

        n4js.add_scope(user.identifier, credential_type, scope)
        n4js.add_scope(user.identifier, credential_type, not_removed)

        n4js.remove_scope(user.identifier, credential_type, scope)

        scopes = n4js.list_scopes(user.identifier, credential_type)
        assert scope not in scopes
        assert not_removed in scopes

    @pytest.mark.parametrize(
        "credential_type", [CredentialedUserIdentity, CredentialedComputeIdentity]
    )
    @pytest.mark.parametrize("scope_str", ("*-*-*", "a-*-*", "a-b-*", "a-b-c"))
    def test_remove_scope_duplicate(
        self, n4js: Neo4jStore, credential_type: CredentialedEntity, scope_str: str
    ):
        user = credential_type(
            identifier="bill",
            hashed_key=hash_key("and ted"),
        )

        n4js.create_credentialed_entity(user)

        scope = Scope.from_str(scope_str)
        not_removed = Scope.from_str("scope-not-removed")

        n4js.add_scope(user.identifier, credential_type, scope)
        n4js.add_scope(user.identifier, credential_type, not_removed)

        n4js.remove_scope(user.identifier, credential_type, scope)
        n4js.remove_scope(user.identifier, credential_type, scope)

        scopes = n4js.list_scopes(user.identifier, credential_type)
        assert scope not in scopes
        assert not_removed in scopes

    # status-setting function related tests.
    # would be too much boilerplate to test all the functions individually
    # so we parameterize over the methods

    @pytest.fixture()
    def f_set_task_waiting(self, n4js):
        return n4js.set_task_waiting

    @pytest.fixture()
    def f_set_task_running(self, n4js):
        return n4js.set_task_running

    @pytest.fixture()
    def f_set_task_complete(self, n4js):
        return n4js.set_task_complete

    @pytest.fixture()
    def f_set_task_error(self, n4js):
        return n4js.set_task_error

    @pytest.fixture()
    def f_set_task_invalid(self, n4js):
        return n4js.set_task_invalid

    @pytest.fixture()
    def f_set_task_deleted(self, n4js):
        return n4js.set_task_deleted

    # allowed = [running, invalid, deleted]
    # not allowed = [complete, error]
    @pytest.mark.parametrize(
        "status_func, result_status, allowed",
        [
            ("f_set_task_waiting", TaskStatusEnum.waiting, True),
            ("f_set_task_running", TaskStatusEnum.running, True),
            ("f_set_task_complete", TaskStatusEnum.waiting, False),
            ("f_set_task_error", TaskStatusEnum.waiting, False),
            ("f_set_task_invalid", TaskStatusEnum.invalid, True),
            ("f_set_task_deleted", TaskStatusEnum.deleted, True),
        ],
    )
    def test_set_task_status_from_waiting(
        self,
        n4js: Neo4jStore,
        network_tyk2,
        scope_test,
        status_func,
        result_status,
        allowed,
        request,
    ):
        # request param fixture used to get function fixture.
        neo4j_status_op = request.getfixturevalue(status_func)
        an = network_tyk2
        network_sk = n4js.create_network(an, scope_test)
        taskhub_sk: ScopedKey = n4js.create_taskhub(network_sk)

        transformation = list(an.edges)[0]
        transformation_sk = n4js.get_scoped_key(transformation, scope_test)

        # create 10 tasks
        task_sks = [n4js.create_task(transformation_sk) for i in range(10)]

        if not allowed:
            with pytest.raises(ValueError, match="Cannot set task"):
                neo4j_status_op(task_sks, raise_error=True)

        tasks_statused = neo4j_status_op(task_sks)
        all_status = n4js.get_task_status(task_sks)

        assert all(s == result_status for s in all_status)
        if not allowed:
            assert all(t is None for t in tasks_statused)
        else:
            assert tasks_statused == task_sks

    # allowed = [waiting, complete, error, invalid, deleted]
    @pytest.mark.parametrize(
        "status_func, result_status, allowed",
        [
            ("f_set_task_waiting", TaskStatusEnum.waiting, True),
            ("f_set_task_running", TaskStatusEnum.running, True),
            ("f_set_task_complete", TaskStatusEnum.complete, True),
            ("f_set_task_error", TaskStatusEnum.error, True),
            ("f_set_task_invalid", TaskStatusEnum.invalid, True),
            ("f_set_task_deleted", TaskStatusEnum.deleted, True),
        ],
    )
    def test_set_task_status_from_running(
        self,
        n4js: Neo4jStore,
        network_tyk2,
        scope_test,
        status_func,
        result_status,
        allowed,
        request,
    ):
        # request param fixture used to get function fixture.
        neo4j_status_op = request.getfixturevalue(status_func)
        an = network_tyk2
        network_sk = n4js.create_network(an, scope_test)
        taskhub_sk: ScopedKey = n4js.create_taskhub(network_sk)

        transformation = list(an.edges)[0]
        transformation_sk = n4js.get_scoped_key(transformation, scope_test)

        # create 10 tasks
        task_sks = [n4js.create_task(transformation_sk) for i in range(10)]

        # set all the tasks to running
        n4js.set_task_running(task_sks)

        if not allowed:
            with pytest.raises(ValueError, match="Cannot set task"):
                neo4j_status_op(task_sks, raise_error=True)

        tasks_statused = neo4j_status_op(task_sks)
        all_status = n4js.get_task_status(task_sks)

        assert all(s == result_status for s in all_status)
        if not allowed:
            assert all(t is None for t in tasks_statused)
        else:
            assert tasks_statused == task_sks

    # allowed = [invalid, deleted]
    # not allowed = [waiting, running, error]
    @pytest.mark.parametrize(
        "status_func, result_status, allowed",
        [
            ("f_set_task_waiting", TaskStatusEnum.complete, False),
            ("f_set_task_running", TaskStatusEnum.complete, False),
            ("f_set_task_complete", TaskStatusEnum.complete, True),
            ("f_set_task_error", TaskStatusEnum.complete, False),
            ("f_set_task_invalid", TaskStatusEnum.invalid, True),
            ("f_set_task_deleted", TaskStatusEnum.deleted, True),
        ],
    )
    def test_set_task_status_from_complete(
        self,
        n4js: Neo4jStore,
        network_tyk2,
        scope_test,
        status_func,
        result_status,
        allowed,
        request,
    ):
        # request param fixture used to get function fixture.
        neo4j_status_op = request.getfixturevalue(status_func)
        an = network_tyk2
        network_sk = n4js.create_network(an, scope_test)
        taskhub_sk: ScopedKey = n4js.create_taskhub(network_sk)

        transformation = list(an.edges)[0]
        transformation_sk = n4js.get_scoped_key(transformation, scope_test)

        # create 10 tasks
        task_sks = [n4js.create_task(transformation_sk) for i in range(10)]

        # set all the tasks to running
        n4js.set_task_running(task_sks)

        # set all the tasks to complete
        n4js.set_task_complete(task_sks)

        if not allowed:
            with pytest.raises(ValueError, match="Cannot set task"):
                neo4j_status_op(task_sks, raise_error=True)

        tasks_statused = neo4j_status_op(task_sks)
        all_status = n4js.get_task_status(task_sks)

        assert all(s == result_status for s in all_status)
        if not allowed:
            assert all(t is None for t in tasks_statused)
        else:
            assert tasks_statused == task_sks

    # allowed = [invalid, deleted, waiting]
    # not allowed = [running, complete]
    @pytest.mark.parametrize(
        "status_func, result_status, allowed",
        [
            ("f_set_task_waiting", TaskStatusEnum.waiting, True),
            ("f_set_task_running", TaskStatusEnum.error, False),
            ("f_set_task_complete", TaskStatusEnum.error, False),
            ("f_set_task_error", TaskStatusEnum.error, True),
            ("f_set_task_invalid", TaskStatusEnum.invalid, True),
            ("f_set_task_deleted", TaskStatusEnum.deleted, True),
        ],
    )
    def test_set_task_status_from_error(
        self,
        n4js: Neo4jStore,
        network_tyk2,
        scope_test,
        status_func,
        result_status,
        allowed,
        request,
    ):
        # request param fixture used to get function fixture.
        neo4j_status_op = request.getfixturevalue(status_func)
        an = network_tyk2
        network_sk = n4js.create_network(an, scope_test)
        taskhub_sk: ScopedKey = n4js.create_taskhub(network_sk)

        transformation = list(an.edges)[0]
        transformation_sk = n4js.get_scoped_key(transformation, scope_test)

        # create 10 tasks
        task_sks = [n4js.create_task(transformation_sk) for i in range(10)]

        # set all the tasks to running
        n4js.set_task_running(task_sks)

        # set all the tasks to error
        n4js.set_task_error(task_sks)

        if not allowed:
            with pytest.raises(ValueError, match="Cannot set task"):
                neo4j_status_op(task_sks, raise_error=True)

        tasks_statused = neo4j_status_op(task_sks)
        all_status = n4js.get_task_status(task_sks)

        assert all(s == result_status for s in all_status)
        if not allowed:
            assert all(t is None for t in tasks_statused)
        else:
            assert tasks_statused == task_sks

    @pytest.mark.parametrize(
        "terminal_status_func, terminal_status",
        [
            ("f_set_task_invalid", TaskStatusEnum.invalid),
            ("f_set_task_deleted", TaskStatusEnum.deleted),
        ],
    )
    @pytest.mark.parametrize(
        "status_func, result_status",
        [
            ("f_set_task_waiting", None),
            ("f_set_task_running", None),
            ("f_set_task_complete", None),
            ("f_set_task_error", None),
            ("f_set_task_invalid", TaskStatusEnum.invalid),
            ("f_set_task_deleted", TaskStatusEnum.deleted),
        ],
    )
    def test_set_task_status_from_terminals(
        self,
        n4js: Neo4jStore,
        network_tyk2,
        scope_test,
        terminal_status_func,
        terminal_status,
        status_func,
        result_status,
        request,
    ):
        # request param fixture used to get function fixture.
        neo4j_status_op = request.getfixturevalue(status_func)
        neo4j_terminal_op = request.getfixturevalue(terminal_status_func)

        an = network_tyk2
        network_sk = n4js.create_network(an, scope_test)
        taskhub_sk: ScopedKey = n4js.create_taskhub(network_sk)

        transformation = list(an.edges)[0]
        transformation_sk = n4js.get_scoped_key(transformation, scope_test)

        # create 10 tasks
        task_sks = [n4js.create_task(transformation_sk) for i in range(10)]

        # move it to one of the terminal statuses
        neo4j_terminal_op(task_sks)

        if not neo4j_status_op == neo4j_terminal_op:
            with pytest.raises(ValueError, match="Cannot set task"):
                neo4j_status_op(task_sks, raise_error=True)

        tasks_statused = neo4j_status_op(task_sks)
        all_status = n4js.get_task_status(task_sks)

        if not neo4j_status_op == neo4j_terminal_op:
            assert all(s == terminal_status for s in all_status)
            assert all(t is None for t in tasks_statused)
        else:
            assert tasks_statused == task_sks
            assert all(s == result_status for s in all_status)

    # check that setting complete, invalid or deleted removes the
    # actions relationship with taskhub
    def test_set_task_status_removes_actions_relationship(
        self,
        n4js: Neo4jStore,
        network_tyk2,
        scope_test,
    ):
        an = network_tyk2
        network_sk = n4js.create_network(an, scope_test)
        taskhub_sk: ScopedKey = n4js.create_taskhub(network_sk)

        transformation = list(an.edges)[0]
        transformation_sk = n4js.get_scoped_key(transformation, scope_test)

        # create 3 tasks
        task_sks = [n4js.create_task(transformation_sk) for i in range(3)]

        n4js.action_tasks(task_sks, taskhub_sk)

        csid = ComputeServiceID("claimer")
        n4js.register_computeservice(ComputeServiceRegistration.from_now(csid))

        # claim all the tasks
        n4js.claim_taskhub_tasks(taskhub_sk, csid, count=3)

        q = f"""
        MATCH (taskhub:TaskHub {{_scoped_key: '{taskhub_sk}'}})
        MATCH (taskhub)-[:ACTIONS]->(task:Task)
        return task
        """

        result = n4js.graph.run(q).to_subgraph()
        sks = [ScopedKey.from_str(task.get("_scoped_key")) for task in result.nodes]
        assert set(sks) == set(task_sks)

        # set one to invalid
        n4js.set_task_invalid(task_sks[0:1])
        # set one to deleted
        n4js.set_task_deleted(task_sks[1:2])
        # set one to complete
        n4js.set_task_complete(task_sks[2:3])

        result = n4js.graph.run(q).to_subgraph()
        assert result == None

    def test_set_task_status_removes_actions_relationship_extends(
        self,
        n4js: Neo4jStore,
        network_tyk2,
        scope_test,
    ):
        # tests the ability to action and claim a set of tasks in an
        # EXTENDS chain
        an = network_tyk2
        network_sk = n4js.create_network(an, scope_test)
        taskhub_sk: ScopedKey = n4js.create_taskhub(network_sk)

        transformation = list(an.edges)[0]
        transformation_sk = n4js.get_scoped_key(transformation, scope_test)

        # create 7 tasks that extend in a bifuricating  EXTENDS chain

        first_task = n4js.create_task(transformation_sk)

        layer_two_1 = n4js.create_task(transformation_sk, extends=first_task)
        layer_two_2 = n4js.create_task(transformation_sk, extends=first_task)

        layer_three_1 = n4js.create_task(transformation_sk, extends=layer_two_1)
        layer_three_2 = n4js.create_task(transformation_sk, extends=layer_two_1)
        layer_three_3 = n4js.create_task(transformation_sk, extends=layer_two_2)
        layer_three_4 = n4js.create_task(transformation_sk, extends=layer_two_2)

        collected_sks = [
            first_task,
            layer_two_1,
            layer_two_2,
            layer_three_1,
            layer_three_2,
            layer_three_3,
            layer_three_4,
        ]
        # action the tasks
        actioned_task_sks = n4js.action_tasks(collected_sks, taskhub_sk)

        q = f"""
        MATCH (taskhub:TaskHub {{_scoped_key: '{taskhub_sk}'}})
        MATCH (taskhub)-[:ACTIONS]->(task:Task)
        return task
        """

        result = n4js.graph.run(q).to_subgraph()
        sks = [ScopedKey.from_str(task.get("_scoped_key")) for task in result.nodes]
        assert set(sks) == set(collected_sks)
        assert len(sks) == 7

        # set layer one to invalid, this should invalidate the entire chain
        n4js.set_task_invalid([first_task])

        result = n4js.graph.run(q).to_subgraph()
        assert result == None

        q = f"""
        MATCH (task:Task)
        WHERE task.status = 'invalid'
        return task
        """
        result = n4js.graph.run(q).to_subgraph()
        sks = [ScopedKey.from_str(task.get("_scoped_key")) for task in result.nodes]
        assert set(sks) == set(collected_sks)
        assert len(sks) == 7

    # check that the status is set correctly through the generic method
    # NOTE: a precondition operation is used for `complete`,`error` as these
    # are not reachable from the default status of `waiting`
    @pytest.mark.parametrize(
        "status, precondition_op",
        [
            (TaskStatusEnum.waiting, None),
            (TaskStatusEnum.running, None),
            (TaskStatusEnum.error, "f_set_task_running"),
            (TaskStatusEnum.complete, "f_set_task_running"),
            (TaskStatusEnum.invalid, None),
            (TaskStatusEnum.deleted, None),
        ],
    )
    def test_set_task_status(
        self,
        n4js: Neo4jStore,
        network_tyk2,
        scope_test,
        status,
        precondition_op,
        request,
    ):
        an = network_tyk2
        network_sk = n4js.create_network(an, scope_test)
        taskhub_sk: ScopedKey = n4js.create_taskhub(network_sk)

        transformation = list(an.edges)[0]
        transformation_sk = n4js.get_scoped_key(transformation, scope_test)

        # create a single task
        task_sk = n4js.create_task(transformation_sk)

        # request param fixture used to get function fixture.
        if precondition_op:
            precondition_op = request.getfixturevalue(precondition_op)
            precondition_op([task_sk])

        # set the status
        n4js.set_task_status([task_sk], status)

        # check the status
        assert n4js.get_task_status([task_sk])[0] == status

    def test_get_task_status(
        self,
        n4js: Neo4jStore,
        network_tyk2,
        scope_test,
    ):
        an = network_tyk2
        network_sk = n4js.create_network(an, scope_test)
        taskhub_sk: ScopedKey = n4js.create_taskhub(network_sk)

        transformation = list(an.edges)[0]
        transformation_sk = n4js.get_scoped_key(transformation, scope_test)

        # create 6 tasks
        task_sks = [n4js.create_task(transformation_sk) for i in range(6)]

        # task 0 will remain waiting

        # task 1 will be set to running
        n4js.set_task_running(task_sks[1:2])

        # task 2 will be set to error
        n4js.set_task_running(task_sks[2:3])
        n4js.set_task_error(task_sks[2:3])

        # task 3 will be set to complete
        n4js.set_task_running(task_sks[3:4])
        n4js.set_task_complete(task_sks[3:4])

        # task 4 will be set to invalid
        n4js.set_task_invalid(task_sks[4:5])

        # task 5 will be set to deleted
        n4js.set_task_deleted(task_sks[5:6])

        # now lets try get them back as a list of statuses
        task_statuses = n4js.get_task_status(task_sks)

        assert task_statuses[0] == TaskStatusEnum.waiting
        assert task_statuses[1] == TaskStatusEnum.running
        assert task_statuses[2] == TaskStatusEnum.error
        assert task_statuses[3] == TaskStatusEnum.complete
        assert task_statuses[4] == TaskStatusEnum.invalid
        assert task_statuses[5] == TaskStatusEnum.deleted
